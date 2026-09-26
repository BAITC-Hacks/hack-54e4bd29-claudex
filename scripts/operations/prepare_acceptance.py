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
PROJECT_PATTERN = re.compile(r"phase8-[a-z0-9][a-z0-9-]{4,50}[a-z0-9]")
DIGEST_PATTERN = re.compile(r"sha256:[a-f0-9]{64}")
ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "tmp" / "acceptance"
REALM_TEMPLATE = ROOT / "infrastructure" / "keycloak" / "realm-medsignal-dev.json"


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
        raise RuntimeError(
            f"Acceptance command failed ({command[0]}, exit {result.returncode})"
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


def _validated_config(project: str, output: Path) -> None:
    rendered = _run(*_compose_command(project, output), "config", "--format", "json")
    validate_compose_config(json.loads(rendered), project)


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
            _validated_config(project, output)
            _run(*_compose_command(project, output), "up", "--no-build", "-d")
            _verify(project, output)
            print(f"Acceptance project {project}: READY (security gate remains FAIL)")
        else:
            _verify(project, output)
            print(f"Acceptance project {project}: READY (security gate remains FAIL)")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        # No paths, env values, Docker stderr or exception text leave this CLI.
        print(f"Acceptance {args.action}: FAIL ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
