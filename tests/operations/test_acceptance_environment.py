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
NAMED_IMAGES = {
    "postgres": "postgres:16-alpine",
    "clickhouse": "clickhouse/clickhouse-server:24.8-alpine",
    "redis": "redis:7.4-alpine",
    "minio": "quay.io/minio/minio:RELEASE.synthetic",
    "minio-init": "quay.io/minio/mc:RELEASE.synthetic",
    "keycloak": "quay.io/keycloak/keycloak:26.0",
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
        prepare_acceptance, "_run_preflight", lambda *_args: None, raising=False
    )
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


def _preflight_fixture(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    output = tmp_path / "phase8-accept-abcd1234"
    output.mkdir()
    (output / "manifest.json").write_text(
        json.dumps({"images": IMAGES, "git_sha": "a" * 40}), encoding="utf-8"
    )
    (output / "realm.json").write_text("{}", encoding="utf-8")
    (output / "source-empty").mkdir()
    repository_config = tmp_path / "nginx.conf"
    repository_config.write_text("synthetic", encoding="utf-8")
    services: dict[str, object] = {
        name: {"image": IMAGES[family]}
        for name, family in prepare_acceptance.SERVICE_IMAGE_FAMILY.items()
    }
    services["nginx"] = {
        "image": IMAGES["nginx"],
        "volumes": [{"type": "bind", "source": str(repository_config)}],
    }
    services["keycloak"] = {
        "image": NAMED_IMAGES["keycloak"],
        "volumes": [{"type": "bind", "source": str(output / "realm.json")}],
    }
    services.update(
        {name: {"image": ref} for name, ref in NAMED_IMAGES.items() if name != "keycloak"}
    )
    return output, {"services": services}


def _fake_preflight_docker(
    *, missing_image: str | None = None, omit_resolved: str | None = None
) -> object:
    def fake_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["docker", "image", "inspect"]:
            image_id = command[3]
            if image_id == missing_image:
                return subprocess.CompletedProcess(
                    command, 1, "", "No such image: POSTGRES_PASSWORD=private-value"
                )
            return subprocess.CompletedProcess(command, 0, image_id + "\n", "")
        if command[-2:] == ["config", "--images"]:
            refs = {*IMAGES.values(), *NAMED_IMAGES.values()}
            if omit_resolved:
                refs.remove(omit_resolved)
            return subprocess.CompletedProcess(command, 0, "\n".join(sorted(refs)), "")
        raise AssertionError("Unexpected preflight command")

    return fake_run


def test_preflight_reports_all_six_local_images_and_matching_compose_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, config = _preflight_fixture(tmp_path)
    monkeypatch.setattr(prepare_acceptance, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        prepare_acceptance, "_compose_command", lambda *_: ["docker", "compose"]
    )
    monkeypatch.setattr(prepare_acceptance.subprocess, "run", _fake_preflight_docker())
    monkeypatch.setattr(
        prepare_acceptance,
        "_check_named_dependency_images",
        lambda *_: None,
        raising=False,
    )
    monkeypatch.setattr(
        prepare_acceptance,
        "_check_daemon_primitives",
        lambda *_: pytest.fail("normal start must not create diagnostic resources"),
        raising=False,
    )
    monkeypatch.setattr(
        prepare_acceptance,
        "_probe_compose_create",
        lambda *_: pytest.fail("normal start must not run compose create/down"),
        raising=False,
    )
    report: dict[str, object] = {}

    prepare_acceptance._run_preflight("phase8-accept-abcd1234", output, config, report)

    assert {item["image_family"] for item in report["image_presence"]} == set(IMAGES)
    assert all(
        item["present"] and item["image_id_matches"] for item in report["image_presence"]
    )
    assert report["compose_image_resolution"]["mismatch"] is False
    assert report["compose_image_resolution"]["expected_image_refs"] == 12
    assert report["compose_image_resolution"]["resolved_image_refs"] == 12
    assert all(item["source_exists"] for item in report["mount_sources"])


def test_preflight_missing_image_halts_before_compose_up_without_leaking_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output, config = _preflight_fixture(tmp_path)
    monkeypatch.setattr(prepare_acceptance, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        prepare_acceptance, "_compose_command", lambda *_: ["docker", "compose"]
    )
    monkeypatch.setattr(
        prepare_acceptance.subprocess,
        "run",
        _fake_preflight_docker(missing_image=IMAGES["backend"]),
    )
    report: dict[str, object] = {}

    with pytest.raises(prepare_acceptance.AcceptancePreflightError) as caught:
        prepare_acceptance._run_preflight(
            "phase8-accept-abcd1234", output, config, report
        )

    assert caught.value.category == "IMAGE_ID_NOT_PRESENT"
    assert caught.value.stage == "preflight_images"
    assert next(
        item for item in report["image_presence"] if item["image_family"] == "backend"
    ) == {"image_family": "backend", "present": False, "image_id_matches": False}
    assert "private-value" not in json.dumps(report) + str(caught.value)
    assert "private-value" not in "".join(capsys.readouterr())


def test_preflight_detects_compose_image_reference_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, config = _preflight_fixture(tmp_path)
    monkeypatch.setattr(prepare_acceptance, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        prepare_acceptance, "_compose_command", lambda *_: ["docker", "compose"]
    )
    monkeypatch.setattr(
        prepare_acceptance.subprocess,
        "run",
        _fake_preflight_docker(omit_resolved=IMAGES["backend"]),
    )
    report: dict[str, object] = {}

    with pytest.raises(prepare_acceptance.AcceptancePreflightError) as caught:
        prepare_acceptance._run_preflight(
            "phase8-accept-abcd1234", output, config, report
        )

    assert caught.value.category == "IMAGE_REFERENCE_RESOLUTION"
    assert report["compose_image_resolution"]["mismatch"] is True
    assert report["compose_image_resolution"]["resolved_image_refs"] == 11
    assert any(
        item["mismatch"] for item in report["compose_image_resolution"]["services"]
    )


def test_preflight_detects_missing_bind_source_without_recording_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, config = _preflight_fixture(tmp_path)
    config["services"]["nginx"]["volumes"][0]["source"] = str(tmp_path / "absent")
    monkeypatch.setattr(prepare_acceptance, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        prepare_acceptance, "_compose_command", lambda *_: ["docker", "compose"]
    )
    monkeypatch.setattr(prepare_acceptance.subprocess, "run", _fake_preflight_docker())
    report: dict[str, object] = {}

    with pytest.raises(prepare_acceptance.AcceptancePreflightError) as caught:
        prepare_acceptance._run_preflight(
            "phase8-accept-abcd1234", output, config, report
        )

    assert caught.value.category == "MOUNT_SOURCE_MISSING"
    assert {"service": "nginx", "mount_kind": "bind", "source_exists": False} in report[
        "mount_sources"
    ]
    assert str(tmp_path) not in json.dumps(report)


def test_invalid_reference_stderr_is_classified_without_raw_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = "POSTGRES_PASSWORD=private-value invalid reference format"
    monkeypatch.setattr(
        prepare_acceptance.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 1, "", raw),
    )

    with pytest.raises(prepare_acceptance.AcceptanceCommandError) as caught:
        prepare_acceptance._run("docker", "compose", "up", "--no-build", "-d")

    assert caught.value.docker_error_category == "INVALID_REFERENCE"
    assert "private-value" not in str(caught.value) + "".join(capsys.readouterr())


def test_successful_preflight_keeps_original_compose_up_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, config = _preflight_fixture(tmp_path)
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(prepare_acceptance, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(prepare_acceptance, "_validated_config", lambda *_: config)
    monkeypatch.setattr(
        prepare_acceptance, "_run_preflight", lambda *_: None, raising=False
    )
    monkeypatch.setattr(
        prepare_acceptance, "_compose_command", lambda *_: ["docker", "compose"]
    )
    monkeypatch.setattr(
        prepare_acceptance, "_run", lambda *command: calls.append(command) or ""
    )
    monkeypatch.setattr(prepare_acceptance, "_verify", lambda *_: None)

    assert prepare_acceptance.main(["start", "--project", output.name]) == 0
    assert calls == [("docker", "compose", "up", "--no-build", "-d")]


def test_start_persists_only_safe_preflight_failure_and_never_calls_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output, config = _preflight_fixture(tmp_path)
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(prepare_acceptance, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(prepare_acceptance, "_validated_config", lambda *_: config)
    monkeypatch.setattr(prepare_acceptance, "_safe_probe", lambda *_: None)

    def fail_preflight(
        _project: str,
        _output: Path,
        _config: dict[str, object],
        report: dict[str, object],
    ) -> None:
        report["image_presence"] = [
            {"image_family": "backend", "present": False, "image_id_matches": False}
        ]
        raise prepare_acceptance.AcceptancePreflightError(
            "IMAGE_ID_NOT_PRESENT", "preflight_images"
        )

    monkeypatch.setattr(prepare_acceptance, "_run_preflight", fail_preflight)
    monkeypatch.setattr(
        prepare_acceptance, "_run", lambda *command: calls.append(command)
    )

    assert prepare_acceptance.main(["start", "--project", output.name]) == 1
    diagnostic = json.loads(
        (output / "sanitized-diagnostics.json").read_text(encoding="utf-8")
    )
    assert diagnostic["failure_stage"] == "preflight_images"
    assert diagnostic["failure_category"] == "IMAGE_ID_NOT_PRESENT"
    assert diagnostic["command_category"] == "preflight"
    assert diagnostic["preflight"]["image_presence"][0]["present"] is False
    assert calls == []
    recorded = json.dumps(diagnostic) + "".join(capsys.readouterr())
    for forbidden in ("POSTGRES_PASSWORD", "APP_SECRET", "private-value", str(tmp_path)):
        assert forbidden not in recorded


@pytest.mark.parametrize("missing", ["realm.json", "source-empty"])
def test_preflight_requires_generated_bind_sources(
    missing: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, config = _preflight_fixture(tmp_path)
    path = output / missing
    if path.is_dir():
        path.rmdir()
    else:
        path.unlink()
    monkeypatch.setattr(prepare_acceptance, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        prepare_acceptance, "_compose_command", lambda *_: ["docker", "compose"]
    )
    monkeypatch.setattr(prepare_acceptance.subprocess, "run", _fake_preflight_docker())
    report: dict[str, object] = {}

    with pytest.raises(prepare_acceptance.AcceptancePreflightError) as caught:
        prepare_acceptance._run_preflight(
            "phase8-accept-abcd1234", output, config, report
        )

    assert caught.value.category == "MOUNT_SOURCE_MISSING"
    assert any(not item["source_exists"] for item in report["mount_sources"])


@pytest.mark.parametrize(
    ("stderr", "category"),
    [
        ("invalid reference format", "INVALID_REFERENCE"),
        (
            'The container name "/phase8-example" is already in use',
            "CONTAINER_NAME_CONFLICT",
        ),
        ("failed to create network", "NETWORK_CREATE_FAILED"),
        ("failed to create volume", "VOLUME_CREATE_FAILED"),
        ("invalid mount config", "MOUNT_CONFIGURATION_ERROR"),
        ("error response from daemon", "DAEMON_ERROR"),
        ("has neither an image nor a build context", "COMPOSE_VALIDATION_RUNTIME_ERROR"),
    ],
)
def test_new_docker_error_categories_never_include_original_stderr(
    stderr: str, category: str
) -> None:
    raw = f"{stderr} POSTGRES_PASSWORD=private-value"
    assert prepare_acceptance._docker_error_category(raw) == category


def test_missing_named_dependency_is_pulled_and_reinspected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _output, config = _preflight_fixture(tmp_path)
    calls: list[tuple[str, ...]] = []
    pulled = False

    def fake_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        nonlocal pulled
        calls.append(tuple(command))
        if command[:3] == ["docker", "image", "inspect"]:
            if command[3] == NAMED_IMAGES["minio"] and not pulled:
                return subprocess.CompletedProcess(command, 1, "", "No such image")
            return subprocess.CompletedProcess(command, 0, "sha256:" + "a" * 64, "")
        if command[:2] == ["docker", "pull"]:
            assert command[2] == NAMED_IMAGES["minio"]
            pulled = True
            return subprocess.CompletedProcess(command, 0, "ignored pull output", "")
        raise AssertionError("Unexpected Docker command")

    monkeypatch.setattr(prepare_acceptance.subprocess, "run", fake_run)
    report: dict[str, object] = {}

    prepare_acceptance._check_named_dependency_images(config, report)

    rows = report["named_images"]
    assert len(rows) == 6
    assert next(row for row in rows if row["service"] == "minio") == {
        "service": "minio",
        "image_kind": "NAMED_IMAGE",
        "present_before": False,
        "pull_attempted": True,
        "pull_succeeded": True,
        "present_after": True,
        "failure_category": None,
    }
    assert len([call for call in calls if call[:2] == ("docker", "pull")]) == 1
    assert "ignored pull output" not in json.dumps(report)


def test_failed_named_image_pull_stops_before_daemon_and_compose_probes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _output, config = _preflight_fixture(tmp_path)
    calls: list[tuple[str, ...]] = []
    failing_ref = NAMED_IMAGES["postgres"]

    def fake_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(command))
        if command[:3] == ["docker", "image", "inspect"]:
            if command[3] == failing_ref:
                return subprocess.CompletedProcess(command, 1, "", "No such image")
            return subprocess.CompletedProcess(command, 0, "sha256:" + "a" * 64, "")
        if command[:2] == ["docker", "pull"]:
            return subprocess.CompletedProcess(
                command, 1, "", "toomanyrequests POSTGRES_PASSWORD=private-value"
            )
        raise AssertionError("Unexpected Docker command")

    monkeypatch.setattr(prepare_acceptance.subprocess, "run", fake_run)
    report: dict[str, object] = {}

    with pytest.raises(prepare_acceptance.AcceptancePreflightError) as caught:
        prepare_acceptance._check_named_dependency_images(config, report)

    assert caught.value.category == "IMAGE_PULL_RATE_LIMIT"
    assert next(
        row for row in report["named_images"] if row["service"] == "postgres"
    ) == {
        "service": "postgres",
        "image_kind": "NAMED_IMAGE",
        "present_before": False,
        "pull_attempted": True,
        "pull_succeeded": False,
        "present_after": False,
        "failure_category": "IMAGE_PULL_RATE_LIMIT",
    }
    assert not any("create" in call or "up" in call for call in calls)
    assert "private-value" not in json.dumps(report) + str(caught.value) + "".join(
        capsys.readouterr()
    )


@pytest.mark.parametrize(
    ("stderr", "category"),
    [
        ("dial tcp: connection refused", "REGISTRY_UNAVAILABLE"),
        ("manifest unknown", "IMAGE_MANIFEST_UNAVAILABLE"),
        ("pull access denied", "IMAGE_PULL_DENIED"),
        ("toomanyrequests", "IMAGE_PULL_RATE_LIMIT"),
        ("Error response from daemon", "DAEMON_ERROR"),
        ("unexpected registry response", "UNKNOWN_PULL_ERROR"),
    ],
)
def test_pull_failure_classifier_emits_only_fixed_categories(
    stderr: str, category: str
) -> None:
    assert (
        prepare_acceptance._pull_failure_category(
            stderr + " MINIO_ROOT_PASSWORD=private-value"
        )
        == category
    )


def test_named_pull_failure_artifact_contains_only_sanitized_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output, config = _preflight_fixture(tmp_path)
    raw_secret = "MINIO_ROOT_PASSWORD=synthetic-private-value"  # noqa: S105 — test canary
    monkeypatch.setattr(prepare_acceptance, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(prepare_acceptance, "_validated_config", lambda *_: config)
    monkeypatch.setattr(prepare_acceptance, "_safe_probe", lambda *_: None)
    monkeypatch.setattr(prepare_acceptance, "_safe_services", lambda *_: [])

    def fail_pull(
        _project: str,
        _output: Path,
        _config: dict[str, object],
        report: dict[str, object],
    ) -> None:
        raw_stderr = f"toomanyrequests {raw_secret}"
        category = prepare_acceptance._pull_failure_category(raw_stderr)
        report["named_images"] = [
            {
                "service": "minio",
                "image_kind": "NAMED_IMAGE",
                "present_before": False,
                "pull_attempted": True,
                "pull_succeeded": False,
                "present_after": False,
                "failure_category": category,
            }
        ]
        raise prepare_acceptance.AcceptancePreflightError(category, "named_images")

    monkeypatch.setattr(prepare_acceptance, "_run_preflight", fail_pull)
    assert prepare_acceptance.main(["start", "--project", output.name]) == 1

    artifact = (output / "sanitized-diagnostics.json").read_text(encoding="utf-8")
    result = json.loads(artifact)
    assert result["failure_stage"] == "named_images"
    assert result["failure_category"] == "IMAGE_PULL_RATE_LIMIT"
    assert result["preflight"]["named_images"][0]["service"] == "minio"
    assert raw_secret not in artifact + "".join(capsys.readouterr())
