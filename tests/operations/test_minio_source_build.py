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


def test_patched_variant_is_explicit_and_limits_changes_to_go_modules() -> None:
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    patches = manifest["patched_acceptance"]
    assert set(patches) == {"server", "client"}
    for name in ("server", "client"):
        entry = patches[name]
        patch = ROOT / entry["path"]
        assert patch.is_file()
        assert hashlib.sha256(patch.read_bytes()).hexdigest() == entry["sha256"]
        changed = {
            line.removeprefix("diff --git a/").split(" b/", maxsplit=1)[0]
            for line in patch.read_text(encoding="utf-8").splitlines()
            if line.startswith("diff --git a/")
        }
        assert changed == {"go.mod", "go.sum"}
        assert "+go 1.24.0" in patch.read_text(encoding="utf-8")
        assert "+\tgoogle.golang.org/grpc v1.79.3" in patch.read_text(encoding="utf-8")
    assert "+\tgithub.com/rabbitmq/amqp091-go v1.13.0" in (
        ROOT / patches["server"]["path"]
    ).read_text(encoding="utf-8")
    backport = manifest["server_security_backport"]
    assert backport["fix_commit_sha"] == minio_source_build.FIX_COMMIT
    assert backport["changed_files"] == ["cmd/admin-handlers-users.go"]
    assert hashlib.sha256((ROOT / backport["path"]).read_bytes()).hexdigest() == (
        minio_source_build.APP_PATCH_SHA256
    )
    assert backport["patched_source_tree_sha1"] == minio_source_build.PATCHED_SERVER_TREE


def test_patch_validation_accepts_windows_checkout_line_endings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "go.mod").write_bytes(
        b"module github.com/minio/mc\r\ngo 1.24.0\r\ngoogle.golang.org/grpc v1.79.3\r\n"
    )
    monkeypatch.setattr(
        minio_source_build,
        "_run",
        lambda args, **_kwargs: "go.mod\ngo.sum" if "--name-only" in args else "",
    )
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert (
        minio_source_build._apply_acceptance_patch("client", source, manifest)
        == (manifest["patched_acceptance"]["client"]["sha256"])
    )


def test_source_checkout_forces_lf_before_reading_signed_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs: object) -> str:
        calls.append(args)
        if args[:2] == ["git", "rev-parse"]:
            return (
                manifest["server"]["commit_sha"]
                if args[-1].endswith("^{commit}")
                else manifest["server"]["tag_object_sha"]
            )
        return ""

    monkeypatch.setattr(minio_source_build, "_run", fake_run)
    minio_source_build._source("server", manifest, tmp_path, tmp_path / "gnupg")
    clone = next(row for row in calls if "clone" in row)
    assert "--no-checkout" in clone
    config_lf = calls.index(["git", "config", "core.autocrlf", "false"])
    checkout = next(i for i, row in enumerate(calls) if row[:2] == ["git", "checkout"])
    assert config_lf < checkout
    assert calls[config_lf + 1] == ["git", "config", "core.eol", "lf"]


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
    assert 'org.medsignal.acceptance.variant="${PATCH_VARIANT}"' in text
    assert "apk upgrade --no-cache libcrypto3 libssl3" in text
    assert 'google.golang.org/grpc)" = "v1.79.3"' in text
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
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    expected = {"server": "sha256:" + "1" * 64, "client": "sha256:" + "2" * 64}
    rows = {
        name: {
            "tag": f"{PROJECT}-minio-{name}:acceptance",
            "image_id": image_id,
            "tag_object_sha": minio_source_build.EXPECTED[name][2],
            "commit_sha": minio_source_build.EXPECTED[name][3],
            "patch_sha256": manifest["patched_acceptance"][name]["sha256"],
            "security_patch_sha256": (
                minio_source_build.APP_PATCH_SHA256 if name == "server" else None
            ),
            "patched_source_tree_sha1": (
                minio_source_build.PATCHED_SERVER_TREE if name == "server" else None
            ),
            "fix_commit_sha": minio_source_build.FIX_COMMIT if name == "server" else None,
            "security_changed_files": [minio_source_build.APP_FILE]
            if name == "server"
            else None,
        }
        for name, image_id in expected.items()
    }
    (folder / "source-images.json").write_text(
        json.dumps(
            {
                "project": PROJECT,
                "variant": "PATCHED_ACCEPTANCE",
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
                "variant": "PATCHED_ACCEPTANCE",
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


def test_patched_image_manifest_rejects_missing_or_changed_patch_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / PROJECT
    folder.mkdir()
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    ids = {"server": "sha256:" + "1" * 64, "client": "sha256:" + "2" * 64}
    rows = {
        name: {
            "tag": f"{PROJECT}-minio-{name}:acceptance",
            "image_id": image_id,
            "tag_object_sha": minio_source_build.EXPECTED[name][2],
            "commit_sha": minio_source_build.EXPECTED[name][3],
            "patch_sha256": manifest["patched_acceptance"][name]["sha256"],
            "security_patch_sha256": (
                minio_source_build.APP_PATCH_SHA256 if name == "server" else None
            ),
            "patched_source_tree_sha1": (
                minio_source_build.PATCHED_SERVER_TREE if name == "server" else None
            ),
            "fix_commit_sha": minio_source_build.FIX_COMMIT if name == "server" else None,
            "security_changed_files": [minio_source_build.APP_FILE]
            if name == "server"
            else None,
        }
        for name, image_id in ids.items()
    }
    evidence = {
        "project": PROJECT,
        "variant": "PATCHED_ACCEPTANCE",
        "build_contract_sha256": hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),
        "images": rows,
    }
    (folder / "source-images.json").write_text(json.dumps(evidence), encoding="utf-8")
    monkeypatch.setattr(minio_source_build, "BUILD_ROOT", tmp_path)
    monkeypatch.setattr(
        minio_source_build,
        "_image_id",
        lambda tag: ids["server"] if "server" in tag else ids["client"],
    )
    assert minio_source_build.load_built_images(PROJECT) == ids
    rows["client"]["patch_sha256"] = "0" * 64
    (folder / "source-images.json").write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="patch"):
        minio_source_build.load_built_images(PROJECT)
    rows["client"]["patch_sha256"] = manifest["patched_acceptance"]["client"]["sha256"]
    rows["server"]["patched_source_tree_sha1"] = "0" * 40
    (folder / "source-images.json").write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance"):
        minio_source_build.load_built_images(PROJECT)


def test_source_manifest_rejects_unapproved_upstream_or_changed_commit() -> None:
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    minio_source_build.validate_build_contract(manifest)
    manifest["server"]["repository"] = "https://github.com/someone/minio.git"
    with pytest.raises(ValueError, match="source contract"):
        minio_source_build.validate_build_contract(manifest)


def test_source_manifest_rejects_changed_acceptance_patch() -> None:
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    manifest["patched_acceptance"]["client"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="patch contract"):
        minio_source_build.validate_build_contract(manifest)


def test_source_manifest_rejects_changed_application_backport() -> None:
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    manifest["server_security_backport"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="backport contract"):
        minio_source_build.validate_build_contract(manifest)


def test_known_critical_blocks_unmodified_build_but_exact_backport_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dependency-only patch cannot clear an application-code advisory."""
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    with pytest.raises(RuntimeError, match="CVE-2024-55949"):
        minio_source_build.require_no_known_application_critical(manifest)
    minio_source_build.require_no_known_application_critical(manifest, patched=True)
    monkeypatch.setattr(minio_source_build, "BUILD_ROOT", tmp_path)
    monkeypatch.setattr(
        minio_source_build,
        "_trusted_key",
        lambda *_args: pytest.fail("build reached network/source stage"),
    )
    with pytest.raises(RuntimeError, match="CVE-2024-55949"):
        minio_source_build.build(PROJECT, patched=False)
    assert not (tmp_path / PROJECT).exists()
    folder = tmp_path / PROJECT
    folder.mkdir()
    (folder / "source-images.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        minio_source_build,
        "_image_id",
        lambda _tag: pytest.fail("preflight inspected an image before advisory gate"),
    )
    with pytest.raises(RuntimeError, match="CVE-2024-55949"):
        minio_source_build.load_built_images(PROJECT)


def test_cli_reports_known_application_critical_without_stack_or_secrets(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert minio_source_build.main(["build", "--project", PROJECT]) == 2
    output = capsys.readouterr()
    assert "BLOCKED_KNOWN_APPLICATION_CRITICAL CVE-2024-55949" in output.err
    assert "Traceback" not in output.err
    assert "password" not in output.err.lower()


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
