"""Exercise source-built MinIO/mc with scoped synthetic S3 operations only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.operations.minio_source_build import load_built_images
from scripts.operations.prepare_acceptance import (
    ARTIFACTS,
    _compose_command,
    _run,
    validate_project_name,
)

# Executed inside existing application containers with their own scoped service
# credentials. The source contains no credential values and reads no patient data.
MINIO_PROBE = """
import io, os, sys
from minio import Minio
from minio.error import S3Error
role, phase, key = sys.argv[1:4]
c = Minio(os.environ['MINIO_ENDPOINT'], access_key=os.environ['MINIO_ACCESS_KEY'],
          secret_key=os.environ['MINIO_SECRET_KEY'], secure=False)
def denied(call):
    try:
        call()
    except S3Error as exc:
        if exc.code != 'AccessDenied': raise AssertionError('wrong denial') from None
    else:
        raise AssertionError('forbidden S3 operation succeeded')
if role == 'pipeline' and phase == 'seed':
    c.put_object('medsignal-quarantine', key, io.BytesIO(b'synthetic'), 9)
elif phase == 'check':
    if role in ('app', 'worker'):
        response = c.get_object('medsignal-models', key)
        try: assert response.read() == b'synthetic'
        finally: response.close(); response.release_conn()
        denied(lambda: c.put_object('medsignal-models', key+'-forbidden',
                                    io.BytesIO(b'synthetic'), 9))
        denied(lambda: c.stat_object('medsignal-quarantine', key))
    elif role == 'pipeline':
        denied(lambda: c.stat_object('medsignal-quarantine', key))
        denied(lambda: c.put_object('medsignal-models', key+'-forbidden',
                                    io.BytesIO(b'synthetic'), 9))
    else: raise AssertionError('unrecognized role')
else: raise AssertionError('unrecognized phase')
"""

MLFLOW_PROBE = """
import os, sys
import boto3
from botocore.exceptions import ClientError
phase, key = sys.argv[1:3]
c = boto3.client('s3', endpoint_url=os.environ['MLFLOW_S3_ENDPOINT_URL'])
if phase == 'seed':
    c.put_object(Bucket='medsignal-models', Key=key, Body=b'synthetic')
    assert c.get_object(Bucket='medsignal-models', Key=key)['Body'].read() == b'synthetic'
elif phase == 'check':
    try: c.head_object(Bucket='medsignal-quarantine', Key=key)
    except ClientError as exc:
        if exc.response['Error']['Code'] not in ('AccessDenied', '403'):
            raise AssertionError('wrong denial') from None
    else: raise AssertionError('foreign bucket readable')
    c.delete_object(Bucket='medsignal-models', Key=key)
else: raise AssertionError('unrecognized phase')
"""


def _probe(
    project: str, output: Path, service: str, role: str, phase: str, key: str
) -> None:
    command = _compose_command(project, output)
    args = ["python", "-c", MINIO_PROBE, role, phase, key]
    if service == "pipeline":
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
            MINIO_PROBE,
            role,
            phase,
            key,
        )
    elif service == "mlflow":
        _run(*command, "exec", "-T", service, "python", "-c", MLFLOW_PROBE, phase, key)
    else:
        _run(*command, "exec", "-T", service, *args)


def verify(project: str, *, acceptance_root: Path = ARTIFACTS) -> dict[str, Any]:
    """Require healthy source-mode server, policy isolation and bootstrap retry."""
    validate_project_name(project)
    output = acceptance_root / project
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("minio_mode") != "PROJECT_BUILT_SOURCE":
        raise ValueError("MinIO source mode is required for this probe")
    load_built_images(project)
    command = _compose_command(project, output)
    raw = _run(*command, "ps", "--all", "--format", "json")
    services = {
        item["Service"]: item
        for line in raw.splitlines()
        if line.strip()
        for item in [json.loads(line)]
    }
    if not raw or (
        services.get("minio", {}).get("Health") != "healthy"
        or services.get("minio", {}).get("State") != "running"
        or services.get("minio-init", {}).get("State") != "exited"
        or services.get("minio-init", {}).get("ExitCode") != 0
    ):
        raise RuntimeError("MinIO server health or bootstrap failed")
    key = f"synthetic-acceptance/{project}.bin"
    _probe(project, output, "pipeline", "pipeline", "seed", key)
    _probe(project, output, "mlflow", "mlflow", "seed", key)
    # A successful second one-shot run is evidence of idempotent bootstrap.
    _run(*command, "run", "--rm", "--no-deps", "minio-init")
    for service, role in (
        ("backend", "app"),
        ("worker", "worker"),
        ("pipeline", "pipeline"),
        ("mlflow", "mlflow"),
    ):
        _probe(project, output, service, role, "check", key)
    result = {
        "project": project,
        "server_health": "PASS",
        "bootstrap_repeated": True,
        "identities_checked": ["app", "worker", "pipeline", "mlflow"],
        "allowed_s3_operations": "PASS",
        "cross_bucket_denials": "PASS",
        "mlflow_s3_access": "PASS",
    }
    (output / "minio-runtime-summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args(argv)
    try:
        verify(args.project)
        print("Project-built MinIO runtime and policy checks: PASS")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(
            f"Project-built MinIO runtime: FAIL ({type(exc).__name__})", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
