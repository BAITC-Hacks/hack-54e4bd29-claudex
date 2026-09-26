"""Prepare and verify an isolated synthetic MedSignal acceptance Compose project.

Generated secrets, test realm and command output stay in ignored ``tmp/``.
No real dataset is mounted and no existing Compose project is addressed.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

REQUIRED_IMAGES = frozenset(
    {"backend", "worker", "mlflow", "frontend", "nginx", "pipeline"}
)
NAMED_DEPENDENCY_SERVICES = (
    "postgres",
    "clickhouse",
    "redis",
    "minio",
    "minio-init",
    "keycloak",
)
PROJECT_PATTERN = re.compile(r"phase8-[a-z0-9][a-z0-9-]{4,50}[a-z0-9]")
DIGEST_PATTERN = re.compile(r"sha256:[a-f0-9]{64}")
PUBLIC_IMAGE_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._/-]*:[A-Za-z0-9._-]+(?:@sha256:[a-f0-9]{64})?"
)
ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "tmp" / "acceptance"
REALM_TEMPLATE = ROOT / "infrastructure" / "keycloak" / "realm-medsignal-dev.json"
SERVICE_NAMES = frozenset(
    {
        "nginx",
        "frontend",
        "backend",
        "worker",
        "migrate",
        "clickhouse-migrate",
        "postgres",
        "clickhouse",
        "redis",
        "minio",
        "minio-init",
        "mlflow",
        "keycloak",
    }
)
ONE_SHOT_SERVICES = frozenset({"migrate", "clickhouse-migrate", "minio-init"})
SERVICE_IMAGE_FAMILY = {
    "nginx": "nginx",
    "frontend": "frontend",
    "backend": "backend",
    "worker": "worker",
    "migrate": "backend",
    "clickhouse-migrate": "pipeline",
    "mlflow": "mlflow",
}
SAFE_STATES = frozenset({"running", "exited", "created", "restarting", "paused", "dead"})
SAFE_HEALTH = frozenset({"healthy", "unhealthy", "starting"})


class AcceptanceCommandError(RuntimeError):
    """Preserve command failure metadata without retaining raw command output."""

    def __init__(
        self, command_category: str, exit_code: int, docker_error_category: str
    ) -> None:
        self.command_category = command_category
        self.exit_code = exit_code
        self.docker_error_category = docker_error_category
        super().__init__(
            f"Acceptance command failed ({command_category}, exit {exit_code})"
        )


class AcceptancePreflightError(RuntimeError):
    """Report a fixed pre-container category without retaining source values."""

    def __init__(self, category: str, stage: str) -> None:
        self.category = category
        self.stage = stage
        super().__init__(f"Acceptance preflight failed ({category})")


def _command_category(command: tuple[str, ...]) -> str:
    if command[:2] == ("docker", "compose"):
        if command[-3:] == ("up", "--no-build", "-d"):
            return "compose_up"
        return "compose_other"
    if command[:2] == ("docker", "build"):
        return "image_build"
    if command[:3] == ("docker", "image", "inspect"):
        return "image_inspect"
    return "other"


def _docker_error_category(stderr: str) -> str:
    """Classify stderr in memory; never reproduce any of its original bytes."""
    lowered = stderr.lower()
    if "container name" in lowered and "already in use" in lowered:
        return "CONTAINER_NAME_CONFLICT"
    for category, markers in (
        ("PORT_BIND_CONFLICT", ("port is already allocated", "address already in use")),
        ("INVALID_REFERENCE", ("invalid reference format",)),
        ("NETWORK_CREATE_FAILED", ("failed to create network", "error creating network")),
        ("VOLUME_CREATE_FAILED", ("failed to create volume", "error creating volume")),
        (
            "MOUNT_CONFIGURATION_ERROR",
            ("invalid mount config", "bind source path does not exist"),
        ),
        (
            "IMAGE_UNAVAILABLE",
            ("no such image", "no such object", "pull access denied", "manifest unknown"),
        ),
        ("DEPENDENCY_FAILED", ("dependency failed to start", "depends on service")),
        ("DEPENDENCY_UNHEALTHY", ("unhealthy",)),
        ("RESOURCE_EXHAUSTED", ("no space left on device", "out of memory")),
        ("PERMISSION_DENIED", ("permission denied", "access is denied")),
        (
            "COMPOSE_VALIDATION_RUNTIME_ERROR",
            ("has neither an image nor a build context", "invalid project name"),
        ),
        ("DAEMON_ERROR", ("error response from daemon",)),
    ):
        if any(marker in lowered for marker in markers):
            return category
    return "UNCLASSIFIED"


def _pull_failure_category(stderr: str) -> str:
    """Classify only fixed registry/daemon markers; never return Docker text."""
    lowered = stderr.lower()
    for category, markers in (
        ("IMAGE_PULL_RATE_LIMIT", ("toomanyrequests", "rate limit", "too many requests")),
        ("IMAGE_MANIFEST_UNAVAILABLE", ("manifest unknown", "manifest not found")),
        (
            "IMAGE_PULL_DENIED",
            ("pull access denied", "unauthorized:", "authentication required"),
        ),
        (
            "REGISTRY_UNAVAILABLE",
            ("dial tcp", "i/o timeout", "tls handshake timeout", "connection refused"),
        ),
        ("DAEMON_ERROR", ("error response from daemon",)),
    ):
        if any(marker in lowered for marker in markers):
            return category
    return "UNKNOWN_PULL_ERROR"


def _quiet_command(
    *command: str, timeout: int = 30
) -> subprocess.CompletedProcess[str] | None:
    """Keep all Docker stdout/stderr in memory, never print or persist them."""
    try:
        return subprocess.run(  # noqa: S603 — fixed Docker CLI argv, no shell
            list(command),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _safe_probe(*command: str) -> str | None:
    """Return stdout only to an allowlist parser, never to a log or artifact."""
    try:
        result = subprocess.run(  # noqa: S603 — fixed local diagnostic argv
            list(command),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _safe_version(output: str | None, pattern: str) -> str | None:
    match = re.search(pattern, output or "", flags=re.IGNORECASE)
    return match.group(1) if match else None


def _safe_services(
    project: str, output: Path, images: dict[str, Any]
) -> list[dict[str, Any]]:
    raw = _safe_probe(
        *_compose_command(project, output), "ps", "--all", "--format", "json"
    )
    if not raw:
        return []
    try:
        parsed = (
            json.loads(raw)
            if raw.lstrip().startswith("[")
            else [json.loads(line) for line in raw.splitlines() if line.strip()]
        )
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    services: dict[str, dict[str, Any]] = {}
    for item in parsed:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("Service"), str)
            or item["Service"] not in SERVICE_NAMES
        ):
            continue
        name = item["Service"]
        state = item.get("State")
        health = item.get("Health")
        code = item.get("ExitCode")
        observed_image = item.get("Image")
        expected_image = images.get(SERVICE_IMAGE_FAMILY.get(name, ""))
        image_id = (
            observed_image
            if isinstance(observed_image, str)
            and DIGEST_PATTERN.fullmatch(observed_image)
            else expected_image
            if isinstance(expected_image, str)
            and DIGEST_PATTERN.fullmatch(expected_image)
            else None
        )
        services[name] = {
            "service": name,
            "state": state
            if isinstance(state, str) and state in SAFE_STATES
            else "unknown",
            "exit_code": code if type(code) is int and 0 <= code <= 255 else None,
            "health": health
            if isinstance(health, str) and health in SAFE_HEALTH
            else "unknown",
            "image_id": image_id,
        }
    return [services[name] for name in sorted(services)]


def _collect_start_diagnostics(
    project: str,
    output: Path,
    stage: str,
    error: Exception,
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a machine-readable report from fixed vocabulary and vetted identifiers."""
    try:
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    manifest = manifest if isinstance(manifest, dict) else {}
    images = manifest.get("images")
    images = images if isinstance(images, dict) else {}
    sha = manifest.get("git_sha")
    sha = sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) else None
    services = _safe_services(project, output, images)
    failed = [
        item["service"]
        for item in services
        if (item["exit_code"] is not None and item["exit_code"] > 0)
        or item["health"] == "unhealthy"
    ]
    command_error = error if isinstance(error, AcceptanceCommandError) else None
    preflight_error = error if isinstance(error, AcceptancePreflightError) else None
    return {
        "diagnostic_version": 1,
        "failure_stage": preflight_error.stage if preflight_error else stage,
        "failure_category": (
            preflight_error.category
            if preflight_error
            else command_error.docker_error_category
            if command_error
            else "UNCLASSIFIED"
        ),
        "command_category": command_error.command_category
        if command_error
        else "preflight"
        if preflight_error
        else "verification",
        "exit_code": command_error.exit_code if command_error else None,
        "docker_error_category": (
            command_error.docker_error_category if command_error else "UNCLASSIFIED"
        ),
        "docker_version": _safe_version(
            _safe_probe("docker", "--version"),
            r"Docker version v?([0-9]+(?:\.[0-9]+){1,3})",
        ),
        "compose_version": _safe_version(
            _safe_probe("docker", "compose", "version"),
            r"Docker Compose version v?([0-9]+(?:\.[0-9]+){1,3})",
        ),
        "project": project,
        "git_sha": sha,
        "services": services,
        "failed_services": failed,
        "failed_dependency_services": [
            name for name in failed if name in ONE_SHOT_SERVICES
        ],
        "preflight": preflight or {},
    }


def validate_project_name(project: str) -> str:
    """Require a project-local namespace for disposable acceptance resources."""
    if PROJECT_PATTERN.fullmatch(project) is None:
        raise ValueError("Acceptance project must use a phase8- namespace")
    return project


def _secret() -> str:
    return secrets.token_urlsafe(48)


def _write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def prepare_files(
    *,
    project: str,
    port: int,
    images: dict[str, str],
    output: Path,
    realm_template: Path,
) -> dict[str, Any]:
    """Generate acceptance configuration without touching existing services."""
    validate_project_name(project)
    if not 1024 <= port <= 65535:
        raise ValueError("Acceptance port must be unprivileged")
    if set(images) != REQUIRED_IMAGES or any(
        DIGEST_PATTERN.fullmatch(digest) is None for digest in images.values()
    ):
        raise ValueError("Acceptance images must be exact sha256 content digests")
    output.mkdir(parents=True, exist_ok=False)
    public_origin = f"http://127.0.0.1:{port}"
    issuer = f"{public_origin}/auth/realms/medsignal"
    realm = json.loads(realm_template.read_text(encoding="utf-8"))
    for user in realm.get("users", []):
        for credential in user.get("credentials", []):
            if credential.get("type", "password") == "password":
                credential["value"] = _secret()
    for client in realm.get("clients", []):
        if client.get("secret"):
            client["secret"] = _secret()
        if client.get("clientId") == "medsignal-frontend":
            client["redirectUris"] = [f"{public_origin}/*"]
            client["webOrigins"] = [public_origin]
            client.setdefault("attributes", {})["post.logout.redirect.uris"] = (
                f"{public_origin}/*"
            )
    _write_private(output / "realm.json", json.dumps(realm, indent=2) + "\n")

    suffix = project.removeprefix("phase8-").replace("-", "")[-12:]
    env = {
        "APP_ENV": "local",
        "APP_DEBUG": "false",
        "APP_SECRET": _secret(),
        "LOG_FORMAT": "json",
        "HTTP_PORT": str(port),
        "CORS_ALLOWED_ORIGINS": public_origin,
        "TRUSTED_HOSTS": "127.0.0.1,localhost",
        "POSTGRES_DB": "medsignal",
        "POSTGRES_USER": "medsignal",
        "POSTGRES_PASSWORD": _secret(),
        "CLICKHOUSE_DB": "medsignal_analytics",
        "CLICKHOUSE_USER": "medsignal",
        "CLICKHOUSE_PASSWORD": _secret(),
        "REDIS_PASSWORD": _secret(),
        "MINIO_ROOT_USER": f"p8root{suffix}",
        "MINIO_ROOT_PASSWORD": _secret(),
        "MINIO_APP_ACCESS_KEY": f"p8app{suffix}",
        "MINIO_APP_SECRET_KEY": _secret(),
        "MINIO_WORKER_ACCESS_KEY": f"p8work{suffix}",
        "MINIO_WORKER_SECRET_KEY": _secret(),
        "MINIO_PIPELINE_ACCESS_KEY": f"p8pipe{suffix}",
        "MINIO_PIPELINE_SECRET_KEY": _secret(),
        "MINIO_MLFLOW_ACCESS_KEY": f"p8model{suffix}",
        "MINIO_MLFLOW_SECRET_KEY": _secret(),
        "KEYCLOAK_ADMIN_USER": f"p8admin{suffix}",
        "KEYCLOAK_ADMIN_PASSWORD": _secret(),
        "KEYCLOAK_PUBLIC_URL": f"{public_origin}/auth",
        "OIDC_ISSUER": issuer,
        "OIDC_INTERNAL_BASE_URL": "http://keycloak:8080/auth/realms/medsignal",
        "AUTH_TEST_MODE": "false",
        "NEXT_PUBLIC_OIDC_ISSUER": issuer,
        "NEXT_PUBLIC_APP_ENV": "test",
        "NEXT_PUBLIC_API_BASE_URL": "/api/v1",
        "DATA_PSEUDONYMIZATION_KEY": _secret(),
        "DATA_SOURCE_DIR_HOST": (output / "source-empty").resolve().as_posix(),
    }
    (output / "source-empty").mkdir()
    _write_private(output / ".env", "".join(f"{k}={v}\n" for k, v in env.items()))

    realm_mount = json.dumps(
        f"{(output / 'realm.json').resolve().as_posix()}:"
        "/opt/keycloak/data/import/realm-medsignal-dev.json:ro"
    )
    backend_command = json.dumps(
        [
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",  # noqa: S104 — container listener, not a host-published port
            "--port",
            "8000",
            "--workers",
            "2",
        ]
    )
    backend_probe = json.dumps(
        [
            "CMD",
            "python",
            "-c",
            "import urllib.request; "
            "urllib.request.urlopen("
            "'http://127.0.0.1:8000/api/v1/health', timeout=3).close()",
        ]
    )
    backend_extra = (
        f"    command: {backend_command}\n"
        "    healthcheck:\n"
        f"      test: {backend_probe}\n"
    )
    image_lines = "".join(
        f"  {service}:\n    build: !reset null\n"
        f"    image: {images[image]}\n"
        + (
            "    volumes: !reset []\n"
            if service in {"frontend", "backend", "worker", "migrate"}
            else ""
        )
        + (backend_extra if service == "backend" else "")
        for service, image in (
            ("frontend", "frontend"),
            ("backend", "backend"),
            ("worker", "worker"),
            ("migrate", "backend"),
            ("clickhouse-migrate", "pipeline"),
            ("mlflow", "mlflow"),
        )
    )
    overlay = (
        "services:\n"
        "  nginx:\n"
        "    build: !reset null\n"
        f"    image: {images['nginx']}\n"
        "    ports: !override\n"
        f"      - \"127.0.0.1:{port}:80\"\n" + image_lines + "  keycloak:\n"
        "    volumes: !override\n"
        f"      - {realm_mount}\n"
    )
    (output / "compose.override.yml").write_text(overlay, encoding="utf-8")
    manifest = {
        "project": project,
        "origin": public_origin,
        "images": images,
        "security_gate": "FAIL",
        "dataset": "synthetic-only",
        "status": "PREPARED",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def validate_compose_config(config: dict[str, Any], project: str) -> None:
    """Reject host data ports or resources outside this project's namespace."""
    validate_project_name(project)
    if config.get("name") != project:
        raise ValueError("Compose project does not match phase8- namespace")
    services = config.get("services")
    if not isinstance(services, dict):
        raise ValueError("Compose services are missing")
    for name, service in services.items():
        ports = service.get("ports") or []
        if name != "nginx" and ports:
            raise ValueError("Acceptance data port or service port published")
        if name == "nginx" and (
            len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1"
        ):
            raise ValueError("Acceptance nginx must bind only loopback")
    for volume in config.get("volumes", {}).values():
        if not isinstance(volume, dict) or not str(volume.get("name", "")).startswith(
            project + "_"
        ):
            raise ValueError("Acceptance volume outside phase8- namespace")


def _run(*command: str) -> str:
    """Execute fixed argv; never reflect Docker stderr, which can contain env."""
    result = subprocess.run(  # noqa: S603
        list(command), cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode:
        category = _command_category(command)
        raise AcceptanceCommandError(
            category,
            result.returncode,
            _docker_error_category(result.stderr)
            if category == "compose_up"
            else "UNCLASSIFIED",
        )
    return result.stdout


def _free_loopback_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _build_images(project: str, port: int) -> dict[str, str]:
    specs = {
        "backend": ("backend/Dockerfile", "backend", "production"),
        "worker": ("infrastructure/ml/Dockerfile", ".", "production"),
        "mlflow": (
            "infrastructure/docker/mlflow.Dockerfile",
            "infrastructure/docker",
            None,
        ),
        "frontend": ("frontend/Dockerfile", "frontend", "production"),
        "nginx": ("infrastructure/nginx/Dockerfile", "infrastructure/nginx", None),
        "pipeline": ("infrastructure/pipeline/Dockerfile", ".", "production"),
    }
    images: dict[str, str] = {}
    for name, (dockerfile, context, target) in specs.items():
        tag = f"{project}-{name}:acceptance"
        command = ["docker", "build", "--pull", "--quiet"]
        if target:
            command += ["--target", target]
        if name == "frontend":
            command += [
                "--build-arg",
                f"NEXT_PUBLIC_OIDC_ISSUER=http://127.0.0.1:{port}/auth/realms/medsignal",
                "--build-arg",
                "NEXT_PUBLIC_APP_ENV=test",
            ]
        command += ["--file", dockerfile, "--tag", tag, context]
        _run(*command)
        digest = _run("docker", "image", "inspect", tag, "--format", "{{.Id}}").strip()
        if DIGEST_PATTERN.fullmatch(digest) is None:
            raise RuntimeError(f"No immutable image digest for {name}")
        images[name] = digest
    return images


def _compose_command(project: str, output: Path) -> list[str]:
    validate_project_name(project)
    if output.resolve() != (ARTIFACTS / project).resolve():
        raise ValueError("Acceptance files must stay in the project artifact directory")
    return [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(output / ".env"),
        "--file",
        str(ROOT / "docker-compose.yml"),
        "--file",
        str(output / "compose.override.yml"),
    ]


def _read_preflight_images(output: Path) -> dict[str, str]:
    try:
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AcceptancePreflightError(
            "MANIFEST_IMAGES_INVALID", "preflight_images"
        ) from exc
    images = manifest.get("images") if isinstance(manifest, dict) else None
    if (
        not isinstance(images, dict)
        or set(images) != REQUIRED_IMAGES
        or any(
            not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value)
            for value in images.values()
        )
    ):
        raise AcceptancePreflightError("MANIFEST_IMAGES_INVALID", "preflight_images")
    return images


def _inspect_local_image(image_id: str) -> tuple[bool, bool, str | None]:
    """Check a pinned ID without retaining Docker's inspect or stderr payload."""
    try:
        result = subprocess.run(  # noqa: S603 — fixed Docker CLI
            ["docker", "image", "inspect", image_id, "--format", "{{.Id}}"],  # noqa: S607 — fixed CLI
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, False, "IMAGE_INSPECT_FAILED"
    if result.returncode:
        category = _docker_error_category(result.stderr)
        if category == "IMAGE_UNAVAILABLE":
            return False, False, "IMAGE_ID_NOT_PRESENT"
        return (
            False,
            False,
            category if category == "DAEMON_ERROR" else "IMAGE_INSPECT_FAILED",
        )
    return True, result.stdout.strip() == image_id, None


def _check_preflight_images(output: Path, report: dict[str, Any]) -> dict[str, str]:
    images = _read_preflight_images(output)
    presence: list[dict[str, Any]] = []
    errors: set[str] = set()
    for family in sorted(REQUIRED_IMAGES):
        present, matches, error = _inspect_local_image(images[family])
        presence.append(
            {"image_family": family, "present": present, "image_id_matches": matches}
        )
        if error:
            errors.add(error)
        elif not matches:
            errors.add("IMAGE_ID_MISMATCH")
    report["image_presence"] = presence
    for category in (
        "DAEMON_ERROR",
        "IMAGE_INSPECT_FAILED",
        "IMAGE_ID_NOT_PRESENT",
        "IMAGE_ID_MISMATCH",
    ):
        if category in errors:
            raise AcceptancePreflightError(category, "preflight_images")
    return images


def _check_preflight_image_resolution(
    project: str,
    output: Path,
    config: dict[str, Any],
    images: dict[str, str],
    report: dict[str, Any],
) -> None:
    raw = _safe_probe(*_compose_command(project, output), "config", "--images")
    resolved = {line.strip() for line in (raw or "").splitlines() if line.strip()}
    services = config.get("services", {})
    rows: list[dict[str, Any]] = []
    expected: set[str] = set()
    mismatch = raw is None or not isinstance(services, dict)
    active_names: set[str] = set()
    if isinstance(services, dict):
        for name, service in sorted(services.items()):
            if name not in SERVICE_NAMES or not isinstance(service, dict):
                mismatch = True
                continue
            if service.get("profiles"):
                continue  # Profile-only tools do not participate in default up.
            active_names.add(name)
            image = service.get("image")
            family = SERVICE_IMAGE_FAMILY.get(name, name)
            if isinstance(image, str) and image:
                expected.add(image)
            kind = (
                "UNKNOWN"
                if not isinstance(image, str) or image not in resolved
                else "LOCAL_IMAGE_ID"
                if DIGEST_PATTERN.fullmatch(image)
                else "NAMED_IMAGE"
            )
            service_mismatch = kind == "UNKNOWN" or (
                name in SERVICE_IMAGE_FAMILY and image != images[family]
            )
            mismatch = mismatch or service_mismatch
            rows.append(
                {
                    "service": name,
                    "expected_image_family": family,
                    "resolved_reference_kind": kind,
                    "mismatch": service_mismatch,
                }
            )
    mismatch = (
        mismatch
        or not expected.issubset(resolved)
        or not set(SERVICE_IMAGE_FAMILY).issubset(active_names)
    )
    report["compose_image_resolution"] = {
        "expected_image_refs": len(expected),
        "resolved_image_refs": len(resolved),
        "services": rows,
        "mismatch": mismatch,
    }
    if mismatch:
        raise AcceptancePreflightError(
            "IMAGE_REFERENCE_RESOLUTION", "preflight_image_resolution"
        )


def _check_preflight_mounts(
    config: dict[str, Any], output: Path, report: dict[str, Any]
) -> None:
    services = config.get("services", {})
    checks: list[dict[str, Any]] = []
    seen: set[tuple[str, Path]] = set()
    if isinstance(services, dict):
        for name, service in sorted(services.items()):
            if (
                name not in SERVICE_NAMES
                or not isinstance(service, dict)
                or service.get("profiles")
            ):
                continue
            volumes = service.get("volumes", [])
            if not isinstance(volumes, list):
                continue
            for volume in volumes:
                if not isinstance(volume, dict) or volume.get("type") != "bind":
                    continue
                source = volume.get("source")
                path = Path(source) if isinstance(source, str) and source else None
                exists = path.exists() if path is not None else False
                checks.append(
                    {"service": name, "mount_kind": "bind", "source_exists": exists}
                )
                if path is not None:
                    seen.add((name, path.resolve()))
    for name, path in (
        ("keycloak", output / "realm.json"),
        ("pipeline", output / "source-empty"),
    ):
        if (name, path.resolve()) not in seen:
            checks.append(
                {"service": name, "mount_kind": "bind", "source_exists": path.exists()}
            )
    report["mount_sources"] = checks
    if any(not item["source_exists"] for item in checks):
        raise AcceptancePreflightError("MOUNT_SOURCE_MISSING", "preflight_mounts")


def _named_image_present(image_ref: str) -> tuple[bool | None, str | None]:
    result = _quiet_command(
        "docker", "image", "inspect", image_ref, "--format", "{{.Id}}", timeout=15
    )
    if result is None:
        return None, "DAEMON_ERROR"
    if result.returncode == 0:
        return (
            (True, None)
            if DIGEST_PATTERN.fullmatch(result.stdout.strip())
            else (None, "DAEMON_ERROR")
        )
    category = _docker_error_category(result.stderr)
    if category == "IMAGE_UNAVAILABLE":
        return False, None
    return None, category if category == "DAEMON_ERROR" else "UNKNOWN_PULL_ERROR"


def _check_named_dependency_images(
    config: dict[str, Any], report: dict[str, Any]
) -> None:
    """Inspect six public named dependencies, pulling only confirmed absent refs."""
    services = config.get("services")
    rows: list[dict[str, Any]] = []
    report["named_images"] = rows
    if not isinstance(services, dict):
        raise AcceptancePreflightError("IMAGE_REFERENCE_RESOLUTION", "named_images")
    for name in NAMED_DEPENDENCY_SERVICES:
        service = services.get(name)
        image_ref = service.get("image") if isinstance(service, dict) else None
        if not isinstance(image_ref, str) or not PUBLIC_IMAGE_PATTERN.fullmatch(
            image_ref
        ):
            raise AcceptancePreflightError("IMAGE_REFERENCE_RESOLUTION", "named_images")
        present, inspect_error = _named_image_present(image_ref)
        row: dict[str, Any] = {
            "service": name,
            "image_kind": "NAMED_IMAGE",
            "present_before": present is True,
            "pull_attempted": False,
            "pull_succeeded": False,
            "present_after": present is True,
            "failure_category": inspect_error,
        }
        rows.append(row)
        if inspect_error:
            raise AcceptancePreflightError(inspect_error, "named_images")
        if present:
            continue
        row["pull_attempted"] = True
        pull = _quiet_command("docker", "pull", image_ref, timeout=600)
        row["pull_succeeded"] = pull is not None and pull.returncode == 0
        after, after_error = _named_image_present(image_ref)
        row["present_after"] = after is True
        if not row["pull_succeeded"] or after is not True:
            category = (
                _pull_failure_category(pull.stderr)
                if pull is not None and pull.returncode
                else after_error or "UNKNOWN_PULL_ERROR"
            )
            row["failure_category"] = category
            raise AcceptancePreflightError(category, "named_images")


def _run_preflight(
    project: str, output: Path, config: dict[str, Any], report: dict[str, Any]
) -> None:
    """Gather only allowlisted evidence before the unchanged Compose up command."""
    images = _check_preflight_images(output, report)
    _check_preflight_image_resolution(project, output, config, images, report)
    _check_preflight_mounts(config, output, report)
    _check_named_dependency_images(config, report)


def _validated_config(project: str, output: Path) -> dict[str, Any]:
    rendered = _run(*_compose_command(project, output), "config", "--format", "json")
    config: dict[str, Any] = json.loads(rendered)
    validate_compose_config(config, project)
    return config


def _wait_http(url: str, *, deadline_seconds: float = 300) -> None:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=3) as response:  # noqa: S310 — loopback-only URL
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        time.sleep(3)
    raise RuntimeError("Acceptance readiness did not reach HTTP 200")


def _verify_services(project: str, output: Path) -> dict[str, str]:
    rendered = _run(*_compose_command(project, output), "ps", "--all", "--format", "json")
    services = {
        item["Service"]: item
        for line in rendered.splitlines()
        if line.strip()
        for item in [json.loads(line)]
    }
    running = {
        "nginx",
        "frontend",
        "backend",
        "worker",
        "postgres",
        "clickhouse",
        "redis",
        "minio",
        "mlflow",
        "keycloak",
    }
    one_shot = {"migrate", "clickhouse-migrate", "minio-init"}
    if any(services.get(name, {}).get("State") != "running" for name in running):
        raise RuntimeError("Acceptance service is not running")
    if any(
        services.get(name, {}).get("State") != "exited"
        or services.get(name, {}).get("ExitCode") != 0
        for name in one_shot
    ):
        raise RuntimeError("Acceptance migration or MinIO identity bootstrap failed")
    return {name: str(item.get("State")) for name, item in services.items()}


def _verify_minio_identities(project: str, output: Path) -> dict[str, str]:
    """Authenticate each non-root service identity against its allowed bucket."""
    command = _compose_command(project, output)
    minio_probe = (
        "import os; from minio import Minio; "
        "client = Minio(os.environ['MINIO_ENDPOINT'], "
        "access_key=os.environ['MINIO_ACCESS_KEY'], "
        "secret_key=os.environ['MINIO_SECRET_KEY'], secure=False); "
        "assert client.bucket_exists('BUCKET')"
    )
    for service, bucket in (
        ("backend", "medsignal-models"),
        ("worker", "medsignal-models"),
    ):
        _run(
            *command,
            "exec",
            "-T",
            service,
            "python",
            "-c",
            minio_probe.replace("BUCKET", bucket),
        )
    _run(
        *command,
        "--profile",
        "tools",
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "pipeline",
        "-c",
        minio_probe.replace("BUCKET", "medsignal-quarantine"),
    )
    mlflow_probe = (
        "import os, boto3; "
        "boto3.client('s3', endpoint_url=os.environ['MLFLOW_S3_ENDPOINT_URL'])"
        ".head_bucket(Bucket='medsignal-models')"
    )
    _run(*command, "exec", "-T", "mlflow", "python", "-c", mlflow_probe)
    return {name: "PASS" for name in ("app", "worker", "pipeline", "mlflow")}


def _verify(project: str, output: Path) -> dict[str, Any]:
    _validated_config(project, output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    origin = manifest["origin"]
    if not origin.startswith("http://127.0.0.1:"):
        raise ValueError("Acceptance origin must be loopback")
    for path in (
        "/api/v1/health",
        "/api/v1/ready",
        "/auth/realms/medsignal/.well-known/openid-configuration",
    ):
        _wait_http(origin + path)
    states = _verify_services(project, output)
    minio_identities = _verify_minio_identities(project, output)
    manifest["status"] = "READY"
    manifest["services"] = states
    manifest["minio_identities"] = minio_identities
    manifest["verified_endpoints"] = ["health", "ready", "keycloak-oidc"]
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "start", "verify"))
    parser.add_argument("--project")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    project = args.project or f"phase8-accept-{uuid.uuid4().hex[:8]}"
    stage = "initialization"
    preflight: dict[str, Any] = {}
    try:
        validate_project_name(project)
        output = ARTIFACTS / project
        if args.action == "prepare":
            if output.exists():
                raise FileExistsError("Acceptance project already exists")
            port = args.port or _free_loopback_port()
            images = _build_images(project, port)
            manifest = prepare_files(
                project=project,
                port=port,
                images=images,
                output=output,
                realm_template=REALM_TEMPLATE,
            )
            manifest["git_sha"] = _run("git", "rev-parse", "HEAD").strip()
            (output / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
            _validated_config(project, output)
            print(f"Prepared isolated acceptance project {project} at {output}")
        elif args.action == "start":
            stage = "compose_config"
            config = _validated_config(project, output)
            stage = "preflight"
            _run_preflight(project, output, config, preflight)
            stage = "compose_up"
            _run(*_compose_command(project, output), "up", "--no-build", "-d")
            stage = "runtime_verify"
            _verify(project, output)
            print(f"Acceptance project {project}: READY (security gate remains FAIL)")
        else:
            _verify(project, output)
            print(f"Acceptance project {project}: READY (security gate remains FAIL)")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        # No paths, env values, Docker stderr or exception text leave this CLI.
        if args.action == "start" and PROJECT_PATTERN.fullmatch(project):
            try:
                output = ARTIFACTS / project
                if output.is_dir():
                    report = _collect_start_diagnostics(
                        project, output, stage, exc, preflight
                    )
                    _write_private(
                        output / "sanitized-diagnostics.json",
                        json.dumps(report, indent=2, sort_keys=True) + "\n",
                    )
                    print(
                        "Acceptance start: FAIL; sanitized diagnostics: "
                        + json.dumps(report, sort_keys=True),
                        file=sys.stderr,
                    )
                    return 1
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                # Even a failed diagnostic probe must not leak original command output.
                pass
        print(f"Acceptance {args.action}: FAIL ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
