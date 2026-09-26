"""Contract checks for a disposable, isolated acceptance Compose project."""

from __future__ import annotations

import json
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
    assert realm["clients"][1]["secret"] != "old-demo"
    assert realm["clients"][0]["redirectUris"] == ["http://127.0.0.1:55123/*"]
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
