"""MinIO principals have only the object-store access their services need."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICIES = ROOT / "infrastructure" / "minio" / "policies"
SERVICE_KEYS = {
    "backend": "APP",
    "worker": "WORKER",
    "ml-runner": "WORKER",
    "pipeline": "PIPELINE",
    "mlflow": "MLFLOW",
}


def _services() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))[
        "services"
    ]


def _resources(policy: str) -> set[str]:
    data = json.loads((POLICIES / f"{policy}.json").read_text(encoding="utf-8"))
    return {
        resource for statement in data["Statement"] for resource in statement["Resource"]
    }


def _actions(policy: str) -> set[str]:
    data = json.loads((POLICIES / f"{policy}.json").read_text(encoding="utf-8"))
    return {action for statement in data["Statement"] for action in statement["Action"]}


def test_application_services_never_receive_minio_root_credentials() -> None:
    services = _services()
    for service, identity in SERVICE_KEYS.items():
        env = services[service]["environment"]
        if service == "mlflow":
            assert env["AWS_ACCESS_KEY_ID"] == "${MINIO_MLFLOW_ACCESS_KEY:?required}"
            assert env["AWS_SECRET_ACCESS_KEY"] == (
                "${MINIO_MLFLOW_SECRET_KEY:?required}"  # noqa: S105 - env reference
            )
        else:
            assert env["MINIO_ACCESS_KEY"] == (
                f"${{MINIO_{identity}_ACCESS_KEY:?required}}"
            )
            assert env["MINIO_SECRET_KEY"] == (
                f"${{MINIO_{identity}_SECRET_KEY:?required}}"
            )
        assert "MINIO_ROOT_USER" not in str(env)
        assert "MINIO_ROOT_PASSWORD" not in str(env)

    init = services["minio-init"]
    assert init["volumes"] == ["./infrastructure/minio:/opt/medsignal/minio:ro"]
    assert services["backend"]["depends_on"]["minio-init"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["worker"]["depends_on"]["minio-init"]["condition"] == (
        "service_completed_successfully"
    )
    production = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    assert "  minio-init:\n" in production
    assert "APP_ENV: production" in production[production.index("  minio-init:\n") :]


def test_bootstrap_treats_generated_secrets_as_positional_values() -> None:
    bootstrap = (ROOT / "infrastructure" / "minio" / "bootstrap.sh").read_text(
        encoding="utf-8"
    )
    assert "mc alias set -- local" in bootstrap
    assert 'mc admin user add -- local "$key" "$secret"' in bootstrap


def test_bucket_policies_do_not_grant_raw_or_cross_role_access() -> None:
    for policy in ("app", "worker", "pipeline", "mlflow"):
        resources = _resources(policy)
        assert "arn:aws:s3:::medsignal-raw" not in resources
        assert "arn:aws:s3:::medsignal-raw/*" not in resources
        assert "arn:aws:s3:::*" not in resources
        assert "arn:aws:s3:::*/*" not in resources

    assert "arn:aws:s3:::medsignal-models/*" in _resources("app")
    assert "arn:aws:s3:::medsignal-models/*" in _resources("worker")
    assert "arn:aws:s3:::medsignal-models/*" in _resources("mlflow")
    assert "arn:aws:s3:::medsignal-quarantine/*" in _resources("pipeline")
    assert "arn:aws:s3:::medsignal-quarantine/*" not in _resources("app")
    assert "arn:aws:s3:::medsignal-models/*" not in _resources("pipeline")
    assert "s3:PutObject" not in _actions("app")
    assert "s3:PutObject" not in _actions("worker")
    assert "s3:GetObject" not in _actions("pipeline")
    assert "s3:PutObject" in _actions("mlflow")
    assert "s3:PutObject" in _actions("pipeline")


def test_local_example_has_distinct_nonroot_service_credentials() -> None:
    env = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.startswith("MINIO_") and "=" in line
    )
    access = [env[f"MINIO_{name}_ACCESS_KEY"] for name in SERVICE_KEYS.values()]
    assert len(set(access)) == 4
    assert env["MINIO_ROOT_USER"] not in access
    assert all(
        "local_dev_only" in env[f"MINIO_{name}_SECRET_KEY"]
        for name in set(SERVICE_KEYS.values())
    )


@pytest.mark.skipif(
    os.environ.get("MEDSIGNAL_MINIO_INTEGRATION") != "1"
    or shutil.which("docker") is None,
    reason="Set MEDSIGNAL_MINIO_INTEGRATION=1 with Docker available",
)
def test_real_minio_denies_cross_bucket_access_and_bootstrap_is_repeatable() -> None:
    """An isolated project proves MinIO enforces the declared S3 policies."""
    project = f"p1-minio-test-{uuid.uuid4().hex[:10]}"
    docker = shutil.which("docker")
    assert docker is not None

    def compose(
        *args: str, env_overrides: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - shell=False; fixed Docker CLI and isolated project
            [
                docker,
                "compose",
                "-p",
                project,
                "--env-file",
                ".env.example",
                *args,
            ],
            cwd=ROOT,
            env={**os.environ, **(env_overrides or {})},
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )

    try:
        for _ in range(2):
            result = compose("up", "-d", "--force-recreate", "minio-init")
            assert result.returncode == 0, result.stderr
            finished = subprocess.run(  # noqa: S603 - fixed Docker CLI, generated name
                [docker, "wait", f"{project}-minio-init-1"],
                capture_output=True,
                text=True,
                timeout=90,
                check=True,
            )
            assert finished.stdout.strip() == "0", compose(
                "logs", "--no-color", "minio-init"
            ).stdout

        # Updating a service secret under the same access key must be a real
        # supported rotation path, not only a documented assumption.
        rotated = {"MINIO_APP_SECRET_KEY": f"{uuid.uuid4().hex}-local_dev_only"}
        result = compose(
            "up",
            "-d",
            "--force-recreate",
            "minio-init",
            env_overrides=rotated,
        )
        assert result.returncode == 0, result.stderr
        finished = subprocess.run(  # noqa: S603 - fixed Docker CLI, generated name
            [docker, "wait", f"{project}-minio-init-1"],
            capture_output=True,
            text=True,
            timeout=90,
            check=True,
        )
        assert finished.stdout.strip() == "0", compose(
            "logs", "--no-color", "minio-init"
        ).stdout

        # All payloads are synthetic; commands suppress any MinIO credential
        # output. A denial is checked by exit code, never by a log snippet.
        probe = r"""
set -eu
mc alias set root http://minio:9000 \
  "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc alias set app http://minio:9000 \
  "$MINIO_APP_ACCESS_KEY" "$MINIO_APP_SECRET_KEY" >/dev/null
mc alias set worker http://minio:9000 \
  "$MINIO_WORKER_ACCESS_KEY" "$MINIO_WORKER_SECRET_KEY" >/dev/null
mc alias set pipeline http://minio:9000 \
  "$MINIO_PIPELINE_ACCESS_KEY" "$MINIO_PIPELINE_SECRET_KEY" >/dev/null
mc alias set mlflow http://minio:9000 \
  "$MINIO_MLFLOW_ACCESS_KEY" "$MINIO_MLFLOW_SECRET_KEY" >/dev/null
printf 'synthetic' | mc pipe mlflow/medsignal-models/least-privilege-test >/dev/null
printf 'synthetic' | mc pipe pipeline/medsignal-quarantine/least-privilege-test >/dev/null
printf 'synthetic' | mc pipe root/medsignal-raw/least-privilege-test >/dev/null
mc ls app >/dev/null
mc cat app/medsignal-models/least-privilege-test >/dev/null
mc cat worker/medsignal-models/least-privilege-test >/dev/null
if mc cat app/medsignal-quarantine/least-privilege-test >/dev/null 2>&1; then exit 10; fi
if mc cat worker/medsignal-quarantine/least-privilege-test \
  >/dev/null 2>&1; then exit 11; fi
if mc cat pipeline/medsignal-quarantine/least-privilege-test \
  >/dev/null 2>&1; then exit 12; fi
if mc cat pipeline/medsignal-models/least-privilege-test \
  >/dev/null 2>&1; then exit 13; fi
if mc cat mlflow/medsignal-quarantine/least-privilege-test \
  >/dev/null 2>&1; then exit 14; fi
if mc cat app/medsignal-raw/least-privilege-test >/dev/null 2>&1; then exit 15; fi
if mc cat worker/medsignal-raw/least-privilege-test >/dev/null 2>&1; then exit 16; fi
if mc cat pipeline/medsignal-raw/least-privilege-test >/dev/null 2>&1; then exit 17; fi
if mc cat mlflow/medsignal-raw/least-privilege-test >/dev/null 2>&1; then exit 18; fi
if printf 'synthetic' | mc pipe app/medsignal-models/no-write \
  >/dev/null 2>&1; then exit 19; fi
if printf 'synthetic' | mc pipe worker/medsignal-models/no-write \
  >/dev/null 2>&1; then exit 20; fi
"""
        result = compose(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "/bin/sh",
            "minio-init",
            "-c",
            probe,
            env_overrides=rotated,
        )
        assert result.returncode == 0, result.stderr
    finally:
        # This unique project was created by the test; no other Compose
        # project or source dataset is ever touched.
        cleanup = compose("down", "--volumes", "--remove-orphans")
        assert cleanup.returncode == 0, cleanup.stderr
