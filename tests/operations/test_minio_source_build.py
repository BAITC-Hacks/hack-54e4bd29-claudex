"""Acceptance-only MinIO source builds never replace production images."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.operations import minio_source_build
from scripts.operations.prepare_acceptance import prepare_files

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "infrastructure/acceptance/minio-source-build.json"
PROJECT = "phase8-accept-abcd1234"
PRODUCT_IMAGES = {
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


def test_provenance_manifest_pins_signed_tag_objects_commits_and_bases() -> None:
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert manifest["platform"] == "linux/amd64"
    assert manifest["go_version"] == "1.24.13"
    assert manifest["signer_fingerprint"] == ("4405F3F0DDBA1B9E68A31D2512C74390F9AAC728")
    assert manifest["builder_image"].startswith("golang:1.24.13-alpine3.22@sha256:")
    assert manifest["runtime_image"].startswith("alpine:3.22.2@sha256:")
    for component in ("server", "client"):
        item = manifest[component]
        assert item["repository"] == (
            "https://github.com/minio/minio.git"
            if component == "server"
            else "https://github.com/minio/mc.git"
        )
        assert len(item["tag_object_sha"]) == 40
        assert len(item["commit_sha"]) == 40
        assert item["tag_object_sha"] != item["commit_sha"]


@pytest.mark.parametrize("name", ["server", "client"])
def test_acceptance_dockerfiles_build_readonly_modules_and_preserve_runtime(
    name: str,
) -> None:
    text = (ROOT / f"infrastructure/acceptance/minio-{name}.Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "--platform=linux/amd64" in text
    assert "@sha256:" in text
    assert "GOTOOLCHAIN=local" in text
    assert "go mod verify" in text
    assert "-mod=readonly" in text
    assert "COPY LICENSE" in text
    assert "COPY NOTICE" in text
    assert "USER 10001:10001" in text
    assert "curl" in text if name == "server" else "/bin/sh" in text


def test_base_compose_retains_official_references() -> None:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "quay.io/minio/minio:RELEASE.2024-11-07T00-52-20Z" in text
    assert "quay.io/minio/mc:RELEASE.2024-11-05T11-29-45Z" in text


def test_explicit_source_mode_replaces_both_images_only_in_isolated_overlay(
    tmp_path: Path,
) -> None:
    realm = tmp_path / "realm.json"
    realm.write_text('{"users":[],"clients":[]}', encoding="utf-8")
    output = tmp_path / PROJECT
    source_ids = {"server": "sha256:" + "1" * 64, "client": "sha256:" + "2" * 64}
    result = prepare_files(
        project=PROJECT,
        port=55123,
        images=PRODUCT_IMAGES,
        output=output,
        realm_template=realm,
        source_images=source_ids,
    )
    overlay = (output / "compose.override.yml").read_text(encoding="utf-8")
    assert "  minio:\n    image: sha256:" + "1" * 64 in overlay
    assert "  minio-init:\n    image: sha256:" + "2" * 64 in overlay
    assert "quay.io/minio/" not in overlay
    assert result["minio_mode"] == "PROJECT_BUILT_SOURCE"
    assert result["minio_source_images"] == source_ids
    assert "ports: !override" in overlay
    assert "volumes: !override" in overlay  # Realm stays test-project scoped.


def test_default_prepare_does_not_replace_quay_images(tmp_path: Path) -> None:
    realm = tmp_path / "realm.json"
    realm.write_text('{"users":[],"clients":[]}', encoding="utf-8")
    output = tmp_path / PROJECT
    result = prepare_files(
        project=PROJECT,
        port=55123,
        images=PRODUCT_IMAGES,
        output=output,
        realm_template=realm,
    )
    overlay = (output / "compose.override.yml").read_text(encoding="utf-8")
    assert "  minio:\n" not in overlay
    assert "  minio-init:\n" not in overlay
    assert result["minio_mode"] == "DEFAULT"


def test_source_image_manifest_rejects_changed_local_image_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / PROJECT
    folder.mkdir()
    expected = {"server": "sha256:" + "1" * 64, "client": "sha256:" + "2" * 64}
    rows = {
        name: {
            "tag": f"{PROJECT}-minio-{name}:acceptance",
            "image_id": image_id,
            "tag_object_sha": minio_source_build.EXPECTED[name][2],
            "commit_sha": minio_source_build.EXPECTED[name][3],
        }
        for name, image_id in expected.items()
    }
    (folder / "source-images.json").write_text(
        json.dumps(
            {
                "project": PROJECT,
                "build_contract_sha256": hashlib.sha256(
                    CONTRACT.read_bytes()
                ).hexdigest(),
                "images": rows,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(minio_source_build, "BUILD_ROOT", tmp_path)
    monkeypatch.setattr(
        minio_source_build,
        "_image_id",
        lambda tag: ("sha256:" + "3" * 64) if "server" in tag else expected["client"],
    )
    with pytest.raises(ValueError, match="does not match"):
        minio_source_build.load_built_images(PROJECT)
    monkeypatch.setattr(
        minio_source_build,
        "_image_id",
        lambda tag: expected["server"] if "server" in tag else expected["client"],
    )
    assert minio_source_build.load_built_images(PROJECT) == expected
    rows["server"]["commit_sha"] = "0" * 40
    (folder / "source-images.json").write_text(
        json.dumps(
            {
                "project": PROJECT,
                "build_contract_sha256": hashlib.sha256(
                    CONTRACT.read_bytes()
                ).hexdigest(),
                "images": rows,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="recorded"):
        minio_source_build.load_built_images(PROJECT)


def test_source_manifest_rejects_unapproved_upstream_or_changed_commit() -> None:
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    minio_source_build.validate_build_contract(manifest)
    manifest["server"]["repository"] = "https://github.com/someone/minio.git"
    with pytest.raises(ValueError, match="source contract"):
        minio_source_build.validate_build_contract(manifest)


def test_source_mode_preflight_never_pulls_quay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.operations import prepare_acceptance

    ids = {"server": "sha256:" + "1" * 64, "client": "sha256:" + "2" * 64}
    services = {
        name: {"image": value}
        for name, value in {
            "postgres": "postgres:16-alpine",
            "clickhouse": "clickhouse/clickhouse-server:24.8-alpine",
            "redis": "redis:7.4-alpine",
            "keycloak": "quay.io/keycloak/keycloak:26.0",
            "minio": ids["server"],
            "minio-init": ids["client"],
        }.items()
    }
    monkeypatch.setattr(
        prepare_acceptance, "_named_image_present", lambda _: (True, None)
    )
    monkeypatch.setattr(
        prepare_acceptance, "_inspect_local_image", lambda _: (True, True, None)
    )
    monkeypatch.setattr(
        prepare_acceptance,
        "_quiet_command",
        lambda *_args, **_kwargs: pytest.fail("source mode tried to pull an image"),
    )
    report: dict[str, object] = {}
    prepare_acceptance._check_named_dependency_images(
        {"services": services}, report, source_images=ids
    )
    named = report["named_images"]
    assert isinstance(named, list)
    assert [row["image_kind"] for row in named if row["service"].startswith("minio")] == [
        "LOCAL_IMAGE_ID",
        "LOCAL_IMAGE_ID",
    ]
