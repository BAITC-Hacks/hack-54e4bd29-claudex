"""Exercise CVE-2024-55949 on a disposable, network-isolated MinIO instance.

This is a pre-Compose gate, not production or external-service testing. All
credentials and exported IAM archives stay in a temporary directory and are
removed even when the probe fails. Docker stdout/stderr are never published.
"""

from __future__ import annotations

import json
import os
import re
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

SAFE_FIELD = re.compile(r"[A-Z_]{2,40}|[a-z_]{2,40}")


class ProbeCommandError(RuntimeError):
    """A Docker command failed; its output may contain secrets and is discarded."""

    def __init__(
        self,
        exit_code: int,
        category: str = "DOCKER_COMMAND_FAILED",
        message: str = "Disposable IAM probe command failed",
    ) -> None:
        self.exit_code = exit_code
        self.category = category
        self.safe_message = message
        super().__init__(message)


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
        raise ProbeCommandError(result.returncode)
    return result


def _write_env(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()), encoding="utf-8"
    )
    path.chmod(0o600)


def _denied(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode == 0:
        return False
    try:
        response = json.loads(result.stdout)
    except (ValueError, TypeError):
        return False
    if not isinstance(response, dict) or response.get("status") != "error":
        return False
    error = response.get("error")
    if not isinstance(error, dict) or error.get("type") != "fatal":
        return False
    cause = error.get("cause")
    if not isinstance(cause, dict):
        return False
    server_error = cause.get("error")
    return isinstance(server_error, dict) and server_error.get("Code") == "AccessDenied"


def _admin_import_valid(result: subprocess.CompletedProcess[str]) -> bool:
    """Require a parseable IAM result with no failed entities."""
    if result.returncode:
        return False
    try:
        value = json.loads(result.stdout)
    except (TypeError, ValueError):
        return False
    if not isinstance(value, dict) or "added" not in value:
        return False
    failed = value.get("failed")
    return isinstance(failed, dict) and not any(failed.values())


def _readwrite_policy(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode:
        return False
    try:
        value = json.loads(result.stdout)
    except (TypeError, ValueError):
        return False
    return isinstance(value, dict) and value.get("policyName") == "readwrite"


def _require_mc(result: subprocess.CompletedProcess[str], message: str) -> None:
    if result.returncode:
        raise ProbeCommandError(result.returncode, "MC_COMMAND_FAILED", message)


def _owned_partial_resource(kind: str, name: str, owner: str) -> bool | None:
    """Check a partially created Docker resource without exposing inspect output."""
    labels = ".Config.Labels" if kind == "container" else ".Labels"
    template = f'{{{{ index {labels} "org.medsignal.acceptance.probe" }}}}'
    command = (
        ("inspect", "--format", template, name)
        if kind == "container"
        else (kind, "inspect", "--format", template, name)
    )
    try:
        inspected = _command(*command, success=False, timeout=10)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return None
    if inspected.returncode:
        return None
    return inspected.stdout.strip() == owner


def _escalation_archive(original: Path, output: Path, limited_user: str) -> None:
    """Use an actual exported IAM ZIP with a synthetic privilege mapping."""
    changed = False
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(output, "w") as target:
        if source.testzip() is not None:
            raise ValueError("IAM export has an invalid ZIP member")
        for info in source.infolist():
            body = source.read(info.filename)
            if info.filename.endswith("user_mappings.json"):
                mappings = json.loads(body)
                if not isinstance(mappings, dict):
                    raise ValueError("IAM export mapping document is invalid")
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
        "--json",
        *args,
        success=False,
    )


def verify(project: str) -> dict[str, Any]:
    """Require scan/review PASS, test deny/allow, then remove all probe state."""
    validate_project_name(project)
    source = BUILD_ROOT / project
    result: dict[str, Any] = {
        "project": project,
        "cve": "CVE-2024-55949",
        "network_exposure": "none (disposable bridge only)",
        "verdict": "ERROR",
        "last_successful_stage": None,
        "failed_stage": "prerequisites",
        "command_exit_code": None,
        "primary_error": None,
        "cleanup_errors": [],
        "cleanup_status": "NOT_RUN",
        "stage_durations_seconds": {},
        "permission_unchanged": None,
        "limited_user_import": "NOT_RUN",
        "service_account_import": "NOT_RUN",
        "admin_import": "NOT_RUN",
        "assertions": {
            "limited_import": "NOT_RUN",
            "service_import": "NOT_RUN",
            "admin_import": "NOT_RUN",
        },
    }
    stage_started = time.monotonic()

    def stage(name: str) -> None:
        nonlocal stage_started
        result["failed_stage"] = name
        stage_started = time.monotonic()

    def passed() -> None:
        result["stage_durations_seconds"][result["failed_stage"]] = round(
            time.monotonic() - stage_started, 3
        )
        result["last_successful_stage"] = result["failed_stage"]
        result["failed_stage"] = None

    network = f"{project}-iam-probe-net"
    volume = f"{project}-iam-probe-data"
    container = f"{project}-iam-probe-server"
    owner = secrets.token_hex(12)
    owner_label = f"org.medsignal.acceptance.probe={owner}"
    created_network = False
    created_volume = False
    started_container = False
    attempted_network = False
    attempted_volume = False
    attempted_container = False
    primary_error: Exception | None = None
    try:
        scan = json.loads(
            (source / "security/scan-summary.json").read_text(encoding="utf-8")
        )
        review = json.loads((source / "advisory-gate.json").read_text(encoding="utf-8"))
        if (
            not scan.get("functional_acceptance_allowed")
            or review.get("synthetic_functional_review") != "PASS"
            or any(scan["images"][name]["critical"] for name in ("server", "client"))
        ):
            raise ValueError("Pre-start MinIO security gate is not satisfied")
        images = load_built_images(project)
        passed()
        stage("create_network")
        attempted_network = True
        _command(
            "network",
            "create",
            "--driver",
            "bridge",
            "--internal",
            "--label",
            f"org.medsignal.acceptance.project={project}",
            "--label",
            owner_label,
            network,
        )
        created_network = True
        passed()
        stage("create_volume")
        attempted_volume = True
        _command(
            "volume",
            "create",
            "--label",
            f"org.medsignal.acceptance.project={project}",
            "--label",
            owner_label,
            volume,
        )
        created_volume = True
        passed()
        with tempfile.TemporaryDirectory(prefix=f"{project}-iam-", dir=source) as temp:
            work = Path(temp)
            root_user = "phase8root"
            root_secret = secrets.token_hex(24)
            limited_user = "phase8limited"
            limited_secret = secrets.token_hex(24)
            service_user = "phase8service"
            # MinIO service-account credentials cap secret keys at 40 chars.
            service_secret = secrets.token_hex(20)
            server_env = work / "server.env"
            _write_env(
                server_env,
                {"MINIO_ROOT_USER": root_user, "MINIO_ROOT_PASSWORD": root_secret},
            )
            stage("start_server")
            attempted_container = True
            _command(
                "run",
                "--detach",
                "--name",
                container,
                "--label",
                owner_label,
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
            passed()
            stage("server_readiness")
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
            passed()
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
            stage("client_readiness")
            _require_mc(
                _mc(client, network, admin_env, work, "--version"),
                "Disposable mc client cannot start",
            )
            passed()
            stage("create_limited_user")
            _require_mc(
                _mc(
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
                ),
                "Disposable limited user creation failed",
            )
            passed()
            stage("attach_policy")
            _require_mc(
                _mc(
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
                ),
                "Disposable limited policy setup failed",
            )
            passed()
            stage("create_service_account")
            _require_mc(
                _mc(
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
                ),
                "Disposable service account creation failed",
            )
            passed()
            stage("verify_limited_authentication")
            bucket = "phase8-iam-probe"
            _require_mc(
                _mc(client, network, admin_env, work, "mb", f"admin/{bucket}"),
                "Disposable IAM control bucket setup failed",
            )
            _require_mc(
                _mc(client, network, limited_env, work, "ls", f"limited/{bucket}"),
                "Limited identity control operation failed",
            )
            passed()
            stage("verify_service_authentication")
            _require_mc(
                _mc(client, network, service_env, work, "ls", f"service/{bucket}"),
                "Service identity control operation failed",
            )
            passed()
            stage("verify_original_permissions")
            before = _mc(
                client,
                network,
                admin_env,
                work,
                "admin",
                "user",
                "info",
                "admin",
                limited_user,
            )
            _require_mc(before, "Limited identity initial policy cannot be verified")
            if not _readwrite_policy(before):
                raise RuntimeError("Limited identity initial policy cannot be verified")
            passed()
            stage("export_iam")
            export = work / "admin-iam-info.zip"
            exported = _mc(
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
            )
            _require_mc(exported, "Disposable IAM export failed")
            if not export.is_file():
                raise RuntimeError("Disposable IAM export failed")
            passed()
            stage("prepare_archive")
            escalation = work / "escalation.zip"
            _escalation_archive(export, escalation, limited_user)
            passed()
            stage("limited_import")
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
            if not _denied(limited):
                result["command_exit_code"] = limited.returncode
                result["assertions"]["limited_import"] = (
                    "FAIL" if limited.returncode == 0 else "ERROR"
                )
                result["limited_user_import"] = (
                    "UNEXPECTED_ALLOW" if limited.returncode == 0 else "ERROR"
                )
                if limited.returncode == 0:
                    raise AssertionError("Restricted IAM import unexpectedly succeeded")
                raise RuntimeError("Restricted IAM import response was not a server deny")
            result["assertions"]["limited_import"] = "PASS"
            result["limited_user_import"] = "DENIED"
            passed()
            stage("service_account_import")
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
            if not _denied(service):
                result["command_exit_code"] = service.returncode
                result["assertions"]["service_import"] = (
                    "FAIL" if service.returncode == 0 else "ERROR"
                )
                result["service_account_import"] = (
                    "UNEXPECTED_ALLOW" if service.returncode == 0 else "ERROR"
                )
                if service.returncode == 0:
                    raise AssertionError("Service IAM import unexpectedly succeeded")
                raise RuntimeError("Service IAM import response was not a server deny")
            result["assertions"]["service_import"] = "PASS"
            result["service_account_import"] = "DENIED"
            passed()
            stage("verify_resulting_permissions")
            after = _mc(
                client,
                network,
                admin_env,
                work,
                "admin",
                "user",
                "info",
                "admin",
                limited_user,
            )
            _require_mc(after, "Restricted identity policy cannot be verified")
            if not _readwrite_policy(after):
                result["permission_unchanged"] = False
                raise AssertionError(
                    "Restricted identity policy changed after IAM import"
                )
            result["permission_unchanged"] = True
            passed()
            stage("admin_positive_control")
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
            _require_mc(admin, "Authorized IAM import was not accepted")
            if not _admin_import_valid(admin):
                raise RuntimeError("Authorized IAM import was not accepted")
            passed()
            result["assertions"] = {
                "limited_import": "PASS",
                "service_import": "PASS",
                "admin_import": "PASS",
            }
            result["admin_import"] = "ALLOWED"
            result["verdict"] = "PASS"
    except Exception as exc:
        primary_error = exc
        if result["failed_stage"] is not None:
            result["stage_durations_seconds"][result["failed_stage"]] = round(
                time.monotonic() - stage_started, 3
            )
        if isinstance(exc, subprocess.TimeoutExpired):
            result["primary_error"] = {"category": "TIMEOUT"}
        else:
            result["primary_error"] = {"category": "PROBE_STAGE_ERROR"}
        if isinstance(exc, AssertionError):
            result["verdict"] = "FAIL"
        result["command_exit_code"] = (
            exc.exit_code
            if isinstance(exc, ProbeCommandError)
            else result["command_exit_code"]
        )
        if isinstance(exc, ProbeCommandError):
            result["primary_error"] = {"category": exc.category}
            if exc.category == "MC_COMMAND_FAILED":
                result["primary_error"]["message"] = exc.safe_message
        elif isinstance(exc, ValueError) and result["failed_stage"] == "prerequisites":
            result["primary_error"] = {"category": "PRESTART_GATE_FAILED"}
        elif isinstance(exc, AssertionError):
            result["primary_error"] = {"category": "IAM_ASSERTION_FAILED"}
    finally:
        result["cleanup_status"] = "PASS"
        partial_container = (
            _owned_partial_resource("container", container, owner)
            if attempted_container and not started_container
            else False
        )
        partial_volume = (
            _owned_partial_resource("volume", volume, owner)
            if attempted_volume and not created_volume
            else False
        )
        partial_network = (
            _owned_partial_resource("network", network, owner)
            if attempted_network and not created_network
            else False
        )
        for kind, ownership in (
            ("CONTAINER", partial_container),
            ("VOLUME", partial_volume),
            ("NETWORK", partial_network),
        ):
            if ownership is None:
                result["cleanup_errors"].append(f"{kind}_OWNERSHIP_UNVERIFIED")
        remove_container = started_container or partial_container is True
        remove_volume = created_volume or partial_volume is True
        remove_network = created_network or partial_network is True
        if remove_container:
            try:
                if _command("rm", "--force", container, success=False).returncode:
                    result["cleanup_errors"].append("CONTAINER_REMOVE_FAILED")
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                result["cleanup_errors"].append("CONTAINER_REMOVE_FAILED")
        if remove_volume:
            try:
                if _command("volume", "rm", volume, success=False).returncode:
                    result["cleanup_errors"].append("VOLUME_REMOVE_FAILED")
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                result["cleanup_errors"].append("VOLUME_REMOVE_FAILED")
        if remove_network:
            try:
                if _command("network", "rm", network, success=False).returncode:
                    result["cleanup_errors"].append("NETWORK_REMOVE_FAILED")
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                result["cleanup_errors"].append("NETWORK_REMOVE_FAILED")
        if result["cleanup_errors"]:
            result["cleanup_status"] = "ERROR"
            result["verdict"] = "ERROR"
        try:
            (source / "iam-probe-summary.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            if primary_error is None:
                raise RuntimeError("Disposable IAM probe summary write failed") from None
    if primary_error is not None:
        raise primary_error
    if result["cleanup_errors"]:
        raise RuntimeError("Disposable IAM probe resource cleanup failed")
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        verify(args.project)
    except Exception:  # Security boundary discards raw exception text.
        try:
            summary = json.loads(
                (BUILD_ROOT / args.project / "iam-probe-summary.json").read_text(
                    encoding="utf-8"
                )
            )
            status = summary.get("verdict")
            stage = summary.get("failed_stage")
            primary = summary.get("primary_error") or {}
            category = primary.get("category") if isinstance(primary, dict) else None
            code = summary.get("command_exit_code")
            if status not in ("ERROR", "FAIL"):
                status = "ERROR"
            if not isinstance(stage, str) or SAFE_FIELD.fullmatch(stage) is None:
                stage = "unknown"
            if not isinstance(category, str) or SAFE_FIELD.fullmatch(category) is None:
                category = "UNKNOWN"
            if not isinstance(code, int) or isinstance(code, bool):
                code = None
            print(
                f"Disposable MinIO IAM regression: {status} "
                f"stage={stage} category={category} exit={code}",
                file=sys.stderr,
            )
        except (OSError, ValueError, TypeError):
            print(
                "Disposable MinIO IAM regression: ERROR summary unavailable",
                file=sys.stderr,
            )
        return 2
    print("Disposable MinIO IAM regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
