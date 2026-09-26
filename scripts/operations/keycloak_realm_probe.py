"""Read-only realm mount and isolated Keycloak import probe for acceptance CI.

Only fixed categories, numeric process metadata and image IDs leave this module.
The generated realm and environment are removed with their phase8 namespace.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from scripts.operations.prepare_acceptance import (
    ARTIFACTS,
    REALM_TEMPLATE,
    ROOT,
    _compose_command,
    _write_private,
    grant_keycloak_realm_read,
    prepare_files,
    validate_project_name,
)

REPORT_ROOT = ROOT / "tmp" / "keycloak-probe"
MOUNT_TARGET = "/opt/keycloak/data/import/realm-medsignal-dev.json"
IMAGE_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
SAFE_IMAGE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*:[A-Za-z0-9._-]+")


def _command(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed Docker argv, no shell
        list(args), cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout
    )


def _require(result: subprocess.CompletedProcess[str], category: str) -> str:
    if result.returncode != 0:
        raise RuntimeError(category)
    return result.stdout.strip()


def _mount(path: Path) -> str:
    return f"type=bind,source={path.resolve()},target={MOUNT_TARGET},readonly"


def _read_probe(
    image: str, realm_path: Path, *, other_user: bool = False
) -> dict[str, Any]:
    command = ["docker", "run", "--rm", "--mount", _mount(realm_path)]
    if other_user:
        command.extend(["--user", "20001:20001"])
    command.extend(
        [
            "--entrypoint",
            "/bin/sh",
            image,
            "-c",
            f"id -u; id -g; stat -c '%u %g %a' {MOUNT_TARGET}; test -r {MOUNT_TARGET}",
        ]
    )
    result = _command(*command)
    lines = result.stdout.splitlines()
    if len(lines) != 3 or any(not re.fullmatch(r"[0-9]+", x) for x in lines[:2]):
        raise RuntimeError("READ_PROBE_ERROR")
    mount_info = lines[2].split()
    if len(mount_info) != 3 or any(not x.isdigit() for x in mount_info):
        raise RuntimeError("READ_PROBE_ERROR")
    if result.returncode not in (0, 1):
        raise RuntimeError("READ_PROBE_ERROR")
    return {
        "uid": int(lines[0]),
        "gid": int(lines[1]),
        "mount_uid": int(mount_info[0]),
        "mount_gid": int(mount_info[1]),
        "mount_mode": mount_info[2],
        "readable": result.returncode == 0,
    }


def _startup_category(logs: str, *, readable: bool, discovery_status: int | None) -> str:
    lowered = logs.lower()
    if not readable and discovery_status != 200:
        return "REALM_FILE_UNREADABLE"
    if any(
        marker in lowered for marker in ("accessdeniedexception", "permission denied")
    ):
        return "REALM_FILE_UNREADABLE"
    if any(marker in lowered for marker in ("jsonparseexception", "invalid json")):
        return "REALM_PARSE_FAILED"
    if discovery_status == 404:
        return "REALM_NOT_IMPORTED"
    if "failed to import" in lowered or "error importing realm" in lowered:
        return "REALM_IMPORT_FAILED"
    if discovery_status == 200:
        return "OIDC_DISCOVERY_OK"
    return "KEYCLOAK_STARTUP_UNVERIFIED"


def _runtime_probe(
    project: str,
    image: str,
    realm_path: Path,
    environment: dict[str, str],
    readable: bool,
) -> dict[str, Any]:
    name = f"{project}-realm-runtime"
    env_path = realm_path.parent / "keycloak.env"
    if any("\n" in str(value) for value in environment.values()):
        raise RuntimeError("INVALID_KEYCLOAK_ENV")
    _write_private(
        env_path, "".join(f"{key}={value}\n" for key, value in environment.items())
    )
    result: dict[str, Any] = {
        "exit_code": None,
        "oom_killed": None,
        "restart_count": None,
        "discovery_status": None,
        "startup_category": "NOT_RUN",
        "cleanup_status": "NOT_RUN",
    }
    created = False
    try:
        _require(
            _command(
                "docker",
                "create",
                "--name",
                name,
                "--restart",
                "no",
                "--env-file",
                str(env_path),
                "--mount",
                _mount(realm_path),
                "-p",
                "127.0.0.1::8080",
                image,
                "start-dev",
                "--import-realm",
            ),
            "CONTAINER_CREATE_FAILED",
        )
        created = True
        _require(_command("docker", "start", name), "CONTAINER_START_FAILED")
        port_result = _require(
            _command("docker", "port", name, "8080/tcp"), "PORT_DISCOVERY_FAILED"
        )
        match = re.fullmatch(r"127\.0\.0\.1:([0-9]+)", port_result)
        if match is None:
            raise RuntimeError("PORT_DISCOVERY_FAILED")
        url = (
            f"http://127.0.0.1:{match.group(1)}"
            "/auth/realms/medsignal/.well-known/openid-configuration"
        )
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            try:
                with urlopen(url, timeout=2) as response:  # noqa: S310 — loopback only
                    result["discovery_status"] = response.status
                if result["discovery_status"] == 200:
                    break
            except HTTPError as exc:
                result["discovery_status"] = exc.code
            except (OSError, URLError):
                pass
            state_probe = _command(
                "docker",
                "inspect",
                name,
                "--format",
                "{{.State.Status}}",
            )
            if state_probe.returncode == 0 and state_probe.stdout.strip() == "exited":
                break
            time.sleep(2)
        inspect = _require(
            _command(
                "docker",
                "inspect",
                name,
                "--format",
                "{{json .State}}|{{.RestartCount}}",
            ),
            "CONTAINER_INSPECT_FAILED",
        )
        state_json, restart_text = inspect.rsplit("|", 1)
        state = json.loads(state_json)
        result["exit_code"] = (
            state.get("ExitCode") if state.get("Status") == "exited" else None
        )
        result["oom_killed"] = state.get("OOMKilled")
        result["restart_count"] = int(restart_text)
        logs = _command("docker", "logs", name, timeout=10)
        result["startup_category"] = _startup_category(
            logs.stdout + logs.stderr if logs.returncode == 0 else "",
            readable=readable,
            discovery_status=result["discovery_status"],
        )
    finally:
        if created:
            cleanup = _command("docker", "rm", "-f", name, timeout=20)
            result["cleanup_status"] = "PASS" if cleanup.returncode == 0 else "FAIL"
    return result


def probe(project: str) -> dict[str, Any]:
    """Run an isolated realm read/import check; return allowlisted evidence only."""
    validate_project_name(project)
    output = ARTIFACTS / project
    if output.exists():
        raise FileExistsError("Probe namespace already exists")
    images = {
        name: "sha256:" + digit * 64
        for name, digit in zip(
            ("backend", "worker", "mlflow", "frontend", "nginx", "pipeline"),
            "abcdef",
            strict=True,
        )
    }
    prepare_files(
        project=project,
        port=55127,
        images=images,
        output=output,
        realm_template=REALM_TEMPLATE,
    )
    realm_path = output / "realm.json"
    try:
        config_text = _require(
            _command(*_compose_command(project, output), "config", "--format", "json"),
            "COMPOSE_CONFIG_FAILED",
        )
        service = json.loads(config_text)["services"]["keycloak"]
        image = service["image"]
        if not isinstance(image, str) or SAFE_IMAGE_PATTERN.fullmatch(image) is None:
            raise RuntimeError("IMAGE_REFERENCE_INVALID")
        if _command("docker", "image", "inspect", image).returncode != 0:
            _require(_command("docker", "pull", image, timeout=180), "IMAGE_PULL_FAILED")
        image_info = _require(
            _command(
                "docker",
                "image",
                "inspect",
                image,
                "--format",
                "{{.Id}}|{{.Config.User}}",
            ),
            "IMAGE_INSPECT_FAILED",
        )
        image_id, image_user = image_info.split("|", 1)
        if IMAGE_ID_PATTERN.fullmatch(image_id) is None:
            raise RuntimeError("IMAGE_INSPECT_FAILED")
        file_stat = realm_path.stat()
        report: dict[str, Any] = {
            "image_reference": image,
            "image_id": image_id,
            "image_user": image_user,
            "realm_owner_uid": file_stat.st_uid,
            "realm_owner_gid": file_stat.st_gid,
            "realm_mode": oct(stat.S_IMODE(file_stat.st_mode)),
            "realm_acl_present": (
                "system.posix_acl_access" in os.listxattr(realm_path)
                if hasattr(os, "listxattr")
                else None
            ),
            "host_uid": os.geteuid() if hasattr(os, "geteuid") else None,
        }
        report["keycloak_user_before"] = _read_probe(image, realm_path)
        report["acl_grant"] = grant_keycloak_realm_read(image, realm_path)
        after_stat = realm_path.stat()
        report["realm_owner_uid_after"] = after_stat.st_uid
        report["realm_owner_gid_after"] = after_stat.st_gid
        report["host_owner_readable_after"] = os.access(realm_path, os.R_OK)
        report["realm_mode_after"] = oct(stat.S_IMODE(after_stat.st_mode))
        report["realm_acl_present_after"] = (
            "system.posix_acl_access" in os.listxattr(realm_path)
            if hasattr(os, "listxattr")
            else None
        )
        ordinary = _read_probe(image, realm_path)
        unrelated = _read_probe(image, realm_path, other_user=True)
        report["keycloak_user_after"] = ordinary
        report["unrelated_user_readable_after"] = unrelated["readable"]
        report["env_mode"] = oct(stat.S_IMODE((output / ".env").stat().st_mode))
        report["runtime"] = _runtime_probe(
            project, image, realm_path, service["environment"], ordinary["readable"]
        )
        report["result"] = (
            "PASS"
            if ordinary["readable"]
            and not unrelated["readable"]
            and report["host_owner_readable_after"]
            and report["realm_owner_uid_after"] == report["realm_owner_uid"]
            and report["env_mode"] == "0o600"
            and report["runtime"]["discovery_status"] == 200
            and report["runtime"]["restart_count"] == 0
            and report["runtime"]["cleanup_status"] == "PASS"
            else "FAIL"
        )
        return report
    finally:
        if output.resolve().parent != ARTIFACTS.resolve():
            raise RuntimeError("Probe cleanup path escaped acceptance namespace")
        shutil.rmtree(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        validate_project_name(args.project)
    except ValueError:
        print('{"result":"ERROR","category":"INVALID_PROJECT_NAME"}')
        return 2
    report: dict[str, Any] = {"result": "ERROR", "category": "NOT_RUN"}
    try:
        report = probe(args.project)
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as exc:
        report = {
            "result": "ERROR",
            "category": str(exc)
            if str(exc)
            in {
                "COMPOSE_CONFIG_FAILED",
                "IMAGE_REFERENCE_INVALID",
                "IMAGE_PULL_FAILED",
                "IMAGE_INSPECT_FAILED",
                "READ_PROBE_ERROR",
                "CONTAINER_CREATE_FAILED",
                "CONTAINER_START_FAILED",
                "PORT_DISCOVERY_FAILED",
                "CONTAINER_INSPECT_FAILED",
                "INVALID_KEYCLOAK_ENV",
            }
            else type(exc).__name__,
        }
    report_path = REPORT_ROOT / args.project / "summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=False)
    _write_private(report_path, json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
