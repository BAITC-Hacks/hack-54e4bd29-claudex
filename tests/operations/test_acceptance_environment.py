"""Contract checks for a disposable, isolated acceptance Compose project."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.operations import prepare_acceptance
from scripts.operations.prepare_acceptance import (
    prepare_files,
    validate_compose_config,
    validate_project_name,
)

ROOT = Path(__file__).resolve().parents[2]
IMAGES = {
    name: "sha256:" + character * 64
    for name, character in {
        "backend": "a",
        "worker": "b",
        "mlflow": "c",
        "frontend": "d",
        "nginx": "e",
        "pipeline": "f",
    }.items()
}


@pytest.mark.parametrize("project", ["medsignal", "phase8", "../phase8-x", "phase8_X"])
def test_acceptance_project_cannot_escape_isolated_namespace(project: str) -> None:
    with pytest.raises(ValueError, match="phase8-"):
        validate_project_name(project)


def test_prepared_files_use_fresh_secrets_scoped_ports_and_pinned_images(
    tmp_path: Path,
) -> None:
    realm_template = tmp_path / "realm-template.json"
    realm_template.write_text(
        json.dumps(
            {
                "realm": "medsignal",
                "users": [
                    {
                        "username": "synthetic-operator",
                        "credentials": [{"value": "old-demo"}],
                    }
                ],
                "clients": [
                    {
                        "clientId": "medsignal-frontend",
                        "redirectUris": ["http://localhost/*"],
                        "webOrigins": ["http://localhost"],
                        "attributes": {"post.logout.redirect.uris": "http://localhost/*"},
                    },
                    {"clientId": "medsignal-dev-cli", "secret": "old-demo"},
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "phase8-accept-abcd1234"
    manifest = prepare_files(
        project="phase8-accept-abcd1234",
        port=55123,
        images=IMAGES,
        output=output,
        realm_template=realm_template,
    )

    env_text = (output / ".env").read_text(encoding="utf-8")
    overlay = (output / "compose.override.yml").read_text(encoding="utf-8")
    realm = json.loads((output / "realm.json").read_text(encoding="utf-8"))
    manifest_text = (output / "manifest.json").read_text(encoding="utf-8")

    assert "local_dev_only" not in env_text
    assert "APP_ENV=local" in env_text
    assert "HTTP_PORT=55123" in env_text
    assert "127.0.0.1:55123:80" in overlay
    assert "sha256:" + "a" * 64 in overlay
    assert "!reset []" in overlay
    assert realm["users"][0]["credentials"][0]["value"] != "old-demo"
    assert realm["clients"][1]["secret"] != "old-demo"  # noqa: S105 — test fixture
    assert realm["clients"][0]["redirectUris"] == ["http://127.0.0.1:55123/*"]
    assert realm["clients"][0]["attributes"]["post.logout.redirect.uris"] == (
        "http://127.0.0.1:55123/*"
    )
    assert manifest["security_gate"] == "FAIL"
    assert "old-demo" not in manifest_text
    assert "POSTGRES_PASSWORD" not in manifest_text
    with pytest.raises(FileExistsError):
        prepare_files(
            project="phase8-accept-abcd1234",
            port=55123,
            images=IMAGES,
            output=output,
            realm_template=realm_template,
        )


def test_compose_config_rejects_data_ports_and_unscoped_volumes() -> None:
    valid = {
        "name": "phase8-accept-abcd1234",
        "services": {
            "nginx": {"ports": [{"host_ip": "127.0.0.1", "published": "55123"}]},
            "postgres": {},
            "clickhouse": {},
            "redis": {},
            "minio": {},
            "mlflow": {},
        },
        "volumes": {"postgres-data": {"name": "phase8-accept-abcd1234_postgres-data"}},
    }
    validate_compose_config(valid, "phase8-accept-abcd1234")
    valid["services"]["postgres"]["ports"] = [{"published": "5432"}]
    with pytest.raises(ValueError, match="data port"):
        validate_compose_config(valid, "phase8-accept-abcd1234")
    valid["services"]["postgres"].pop("ports")
    valid["volumes"]["postgres-data"]["name"] = "medsignal_postgres-data"
    with pytest.raises(ValueError, match="volume"):
        validate_compose_config(valid, "phase8-accept-abcd1234")


def test_frontend_build_accepts_isolated_oidc_issuer() -> None:
    dockerfile = (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
    assert "ARG NEXT_PUBLIC_OIDC_ISSUER" in dockerfile
    assert "NEXT_PUBLIC_OIDC_ISSUER=${NEXT_PUBLIC_OIDC_ISSUER}" in dockerfile


def test_mounted_shell_scripts_use_unix_line_endings() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in attributes
    for path in ROOT.rglob("*.sh"):
        if any(part in {".git", "tmp", "node_modules", ".venv"} for part in path.parts):
            continue
        assert b"\r" not in path.read_bytes(), f"CRLF in {path}"


def test_mlflow_image_installs_driver_used_by_runtime() -> None:
    dockerfile = (ROOT / "infrastructure/docker/mlflow.Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "psycopg[binary]==3.2.*" in dockerfile


def test_minio_identity_probes_use_service_credentials_without_host_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = "phase8-accept-abcd1234"
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(prepare_acceptance, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        prepare_acceptance,
        "_run",
        lambda *command: calls.append(command) or "",
    )

    result = prepare_acceptance._verify_minio_identities(project, tmp_path / project)

    assert result == {name: "PASS" for name in ("app", "worker", "pipeline", "mlflow")}
    assert len(calls) == 4
    assert all("MINIO_ROOT_PASSWORD" not in " ".join(call) for call in calls)
    assert all("--env-file" in call for call in calls)


def test_failed_compose_up_preserves_safe_category_and_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = "POSTGRES_PASSWORD=private-value; port is already allocated"
    monkeypatch.setattr(
        prepare_acceptance.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 23, "", raw),
    )

    with pytest.raises(prepare_acceptance.AcceptanceCommandError) as caught:
        prepare_acceptance._run("docker", "compose", "up", "--no-build", "-d")

    error = caught.value
    assert error.command_category == "compose_up"
    assert error.exit_code == 23
    assert error.docker_error_category == "PORT_BIND_CONFLICT"
    assert "private-value" not in str(error)
    assert "POSTGRES_PASSWORD" not in str(error)


def test_start_failure_records_only_allowlisted_compose_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = "phase8-accept-abcd1234"
    output = tmp_path / project
    output.mkdir()
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "git_sha": "a" * 40,
                "images": {"backend": "sha256:" + "b" * 64},
            }
        ),
        encoding="utf-8",
    )
    raw_stderr_canary = (
        "POSTGRES_PASSWORD=private-value " "MINIO_ROOT_PASSWORD=another-value"
    )
    ps = "\n".join(
        json.dumps(item)
        for item in (
            {
                "Service": "backend",
                "State": "exited",
                "ExitCode": 42,
                "Health": "unhealthy",
                "Status": raw_stderr_canary,
                "Image": "sha256:" + "b" * 64,
                "Environment": {"APP_SECRET": "do-not-print"},
            },
            {
                "Service": "migrate",
                "State": "exited",
                "ExitCode": 1,
                "Health": "",
                "Status": raw_stderr_canary,
            },
            {"Service": raw_stderr_canary, "State": "exited", "ExitCode": 9},
        )
    )

    def fake_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if command[-3:] == ["up", "--no-build", "-d"]:
            return subprocess.CompletedProcess(
                command, 17, "", raw_stderr_canary + " dependency failed to start"
            )
        if command == ["docker", "--version"]:
            return subprocess.CompletedProcess(
                command, 0, "Docker version 28.5.1, build abc", ""
            )
        if command == ["docker", "compose", "version"]:
            return subprocess.CompletedProcess(
                command, 0, "Docker Compose version v2.40.0", ""
            )
        if command[-4:] == ["ps", "--all", "--format", "json"]:
            return subprocess.CompletedProcess(command, 0, ps, "")
        raise AssertionError("Unexpected subprocess")

    monkeypatch.setattr(prepare_acceptance, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(prepare_acceptance, "_validated_config", lambda *_args: None)
    monkeypatch.setattr(
        prepare_acceptance, "_compose_command", lambda *_args: ["docker", "compose"]
    )
    monkeypatch.setattr(prepare_acceptance.subprocess, "run", fake_run)

    assert prepare_acceptance.main(["start", "--project", project]) == 1
    diagnostic_file = output / "sanitized-diagnostics.json"
    report = json.loads(diagnostic_file.read_text(encoding="utf-8"))
    assert report["failure_stage"] == "compose_up"
    assert report["command_category"] == "compose_up"
    assert report["exit_code"] == 17
    assert report["docker_error_category"] == "DEPENDENCY_FAILED"
    assert report["docker_version"] == "28.5.1"
    assert report["compose_version"] == "2.40.0"
    assert report["git_sha"] == "a" * 40
    assert report["failed_dependency_services"] == ["migrate"]
    assert report["failed_services"] == ["backend", "migrate"]
    assert report["services"][0] == {
        "service": "backend",
        "state": "exited",
        "exit_code": 42,
        "health": "unhealthy",
        "image_id": "sha256:" + "b" * 64,
    }
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    stored = diagnostic_file.read_text(encoding="utf-8")
    for forbidden in (
        "POSTGRES_PASSWORD",
        "CLICKHOUSE_PASSWORD",
        "REDIS_PASSWORD",
        "MINIO_ROOT_PASSWORD",
        "MINIO_PIPELINE_SECRET_KEY",
        "KEYCLOAK_ADMIN_PASSWORD",
        "APP_SECRET",
        "DATA_PSEUDONYMIZATION_KEY",
        "private-value",
        "another-value",
        "do-not-print",
    ):
        assert forbidden not in combined + stored
    if os.name != "nt":
        assert not diagnostic_file.stat().st_mode & 0o077
