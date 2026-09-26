"""Acceptance-only MinIO source builds never replace production images."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "infrastructure/acceptance/minio-source-build.json"


def test_provenance_manifest_pins_signed_tag_objects_commits_and_bases() -> None:
    manifest = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert manifest["platform"] == "linux/amd64"
    assert manifest["go_version"] == "1.24.13"
    assert manifest["signer_fingerprint"] == (
        "4405F3F0DDBA1B9E68A31D2512C74390F9AAC728"
    )
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
def test_acceptance_dockerfiles_build_readonly_modules_and_preserve_runtime(name: str) -> None:
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
