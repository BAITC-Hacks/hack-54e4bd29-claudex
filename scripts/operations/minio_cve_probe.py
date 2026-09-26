"""Exercise CVE-2024-55949 on a disposable, network-isolated MinIO instance.

This is a pre-Compose gate, not production or external-service testing. All
credentials and exported IAM archives stay in a temporary directory and are
removed even when the probe fails. Docker stdout/stderr are never published.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from scripts.operations.minio_source_build import BUILD_ROOT, load_built_images
from scripts.operations.prepare_acceptance import validate_project_name


def _command(
    *args: str, success: bool = True, timeout: int = 90
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603 — fixed Docker executable, no shell
        ["docker", *args],  # noqa: S607 — fixed Docker CLI
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if success and result.returncode:
        raise RuntimeError("Disposable IAM probe command failed")
    return result


def _write_env(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()), encoding="utf-8"
    )
    path.chmod(0o600)


def _denied(result: subprocess.CompletedProcess[str]) -> bool:
    output = (result.stdout + result.stderr).lower()
    return result.returncode != 0 and any(
        token in output
        for token in (
            "access denied",
            "accessdenied",
            "not authorized",
            "permission denied",
        )
    )


def _escalation_archive(original: Path, output: Path, limited_user: str) -> None:
    """Use an actual exported IAM ZIP with a synthetic privilege mapping."""
    changed = False
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(output, "w") as target:
        for info in source.infolist():
            body = source.read(info.filename)
            if info.filename.endswith("user_mappings.json"):
                mappings = json.loads(body)
                mappings[limited_user] = {
                    "version": 1,
                    "policy": "consoleAdmin",
                    "updatedAt": "2024-08-13T19:47:10.1Z",
                }
                body = json.dumps(mappings).encode("utf-8")
                changed = True
            target.writestr(info, body)
    if not changed:
        raise ValueError("IAM export does not contain expected mapping document")


def _mc(
    image: str, network: str, env_file: Path, work: Path, *args: str
) -> subprocess.CompletedProcess[str]:
    if os.name != "posix":
        raise RuntimeError("Disposable IAM probe requires a Linux Docker runner")
    # Match the host runner UID so the non-root mc process can read the 0600
    # env file and write the exported ZIP inside the 0700 temporary directory.
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if not callable(getuid) or not callable(getgid):
        raise RuntimeError("Disposable IAM probe cannot resolve runner identity")
    runner_user = f"{getuid()}:{getgid()}"
    return _command(
        "run",
        "--rm",
        "--user",
        runner_user,
        "--network",
        network,
        "--env-file",
        str(env_file),
        "--mount",
        f"type=bind,source={work.resolve()},target=/work",
        "--workdir",
        "/work",
        image,
        *args,
        success=False,
    )


def verify(project: str) -> dict[str, Any]:
    """Require scan/review PASS, test deny/allow, then remove all probe state."""
    validate_project_name(project)
    source = BUILD_ROOT / project
    scan = json.loads((source / "security/scan-summary.json").read_text(encoding="utf-8"))
    review = json.loads((source / "advisory-gate.json").read_text(encoding="utf-8"))
    if (
        not scan.get("functional_acceptance_allowed")
        or not review.get("synthetic_functional_review") == "PASS"
        or any(scan["images"][name]["critical"] for name in ("server", "client"))
    ):
        raise ValueError("Pre-start MinIO security gate is not satisfied")
    images = load_built_images(project)
    network = f"{project}-iam-probe-net"
    volume = f"{project}-iam-probe-data"
    container = f"{project}-iam-probe-server"
    created_network = False
    created_volume = False
    started_container = False
    try:
        _command(
            "network",
            "create",
            "--driver",
            "bridge",
            "--internal",
            "--label",
            f"org.medsignal.acceptance.project={project}",
            network,
        )
        created_network = True
        _command(
            "volume",
            "create",
            "--label",
            f"org.medsignal.acceptance.project={project}",
            volume,
        )
        created_volume = True
        with tempfile.TemporaryDirectory(prefix=f"{project}-iam-", dir=source) as temp:
            work = Path(temp)
            root_user = "phase8root"
            root_secret = secrets.token_hex(24)
            limited_user = "phase8limited"
            limited_secret = secrets.token_hex(24)
            service_user = "phase8service"
            service_secret = secrets.token_hex(24)
            server_env = work / "server.env"
            _write_env(
                server_env,
                {"MINIO_ROOT_USER": root_user, "MINIO_ROOT_PASSWORD": root_secret},
            )
            _command(
                "run",
                "--detach",
                "--name",
                container,
                "--network",
                network,
                "--mount",
                f"type=volume,source={volume},target=/data",
                "--env-file",
                str(server_env),
                images["server"],
                "server",
                "/data",
                "--address",
                ":9000",
            )
            started_container = True
            for _ in range(45):
                ready = _command(
                    "exec",
                    container,
                    "curl",
                    "--fail",
                    "--silent",
                    "http://127.0.0.1:9000/minio/health/ready",
                    success=False,
                    timeout=10,
                )
                if ready.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Disposable MinIO did not become healthy")
            admin_env = work / "admin.env"
            limited_env = work / "limited.env"
            service_env = work / "service.env"
            _write_env(
                admin_env,
                {"MC_HOST_admin": f"http://{root_user}:{root_secret}@{container}:9000"},
            )
            _write_env(
                limited_env,
                {
                    "MC_HOST_limited": f"http://{limited_user}:{limited_secret}@{container}:9000"
                },
            )
            _write_env(
                service_env,
                {
                    "MC_HOST_service": f"http://{service_user}:{service_secret}@{container}:9000"
                },
            )
            client = images["client"]
            if _mc(
                client,
                network,
                admin_env,
                work,
                "admin",
                "user",
                "add",
                "admin",
                limited_user,
                limited_secret,
            ).returncode:
                raise RuntimeError("Disposable limited user creation failed")
            if _mc(
                client,
                network,
                admin_env,
                work,
                "admin",
                "policy",
                "attach",
                "admin",
                "readwrite",
                "--user",
                limited_user,
            ).returncode:
                raise RuntimeError("Disposable limited policy setup failed")
            if _mc(
                client,
                network,
                admin_env,
                work,
                "admin",
                "user",
                "svcacct",
                "add",
                "admin",
                limited_user,
                "--access-key",
                service_user,
                "--secret-key",
                service_secret,
            ).returncode:
                raise RuntimeError("Disposable service account creation failed")
            export = work / "admin-iam-info.zip"
            if (
                _mc(
                    client,
                    network,
                    admin_env,
                    work,
                    "admin",
                    "cluster",
                    "iam",
                    "export",
                    "admin",
                    "--output",
                    "/work/admin-iam-info.zip",
                ).returncode
                or not export.is_file()
            ):
                raise RuntimeError("Disposable IAM export failed")
            escalation = work / "escalation.zip"
            _escalation_archive(export, escalation, limited_user)
            limited = _mc(
                client,
                network,
                limited_env,
                work,
                "admin",
                "cluster",
                "iam",
                "import",
                "limited",
                "/work/escalation.zip",
            )
            service = _mc(
                client,
                network,
                service_env,
                work,
                "admin",
                "cluster",
                "iam",
                "import",
                "service",
                "/work/escalation.zip",
            )
            if not _denied(limited) or not _denied(service):
                raise RuntimeError(
                    "IAM import was not denied to both restricted identities"
                )
            admin = _mc(
                client,
                network,
                admin_env,
                work,
                "admin",
                "cluster",
                "iam",
                "import",
                "admin",
                "/work/admin-iam-info.zip",
            )
            if admin.returncode:
                raise RuntimeError("Authorized IAM import was not accepted")
            result = {
                "project": project,
                "cve": "CVE-2024-55949",
                "network_exposure": "none (disposable bridge only)",
                "limited_user_import": "DENIED",
                "service_account_import": "DENIED",
                "admin_import": "ALLOWED",
                "verdict": "PASS",
            }
    finally:
        cleanup_failed = False
        if started_container:
            cleanup_failed |= (
                _command("rm", "--force", container, success=False).returncode != 0
            )
        if created_volume:
            cleanup_failed |= (
                _command("volume", "rm", volume, success=False).returncode != 0
            )
        if created_network:
            cleanup_failed |= (
                _command("network", "rm", network, success=False).returncode != 0
            )
        if cleanup_failed:
            raise RuntimeError("Disposable IAM probe resource cleanup failed")
    (source / "iam-probe-summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        verify(args.project)
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ):
        print("Disposable MinIO IAM regression: FAIL (details withheld)", file=sys.stderr)
        return 2
    print("Disposable MinIO IAM regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
