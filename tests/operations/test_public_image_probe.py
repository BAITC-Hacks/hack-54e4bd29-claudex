"""Exact public-image registry checks for the browser acceptance runner."""

from __future__ import annotations

import json

import pytest

from scripts.operations import probe_public_images

REFS = {
    "minio": "quay.io/minio/minio:RELEASE.2024-11-07T00-52-20Z",
    "minio-init": "quay.io/minio/mc:RELEASE.2024-11-05T11-29-45Z",
    "keycloak": "quay.io/keycloak/keycloak:26.0",
}


def test_selects_exact_three_public_images_from_rendered_compose() -> None:
    rendered = {"services": {name: {"image": ref} for name, ref in REFS.items()}}
    assert probe_public_images.select_refs(rendered) == REFS


def test_docker_architecture_is_normalized_to_oci_platform() -> None:
    assert probe_public_images.oci_platform("linux", "x86_64") == "linux/amd64"
    assert probe_public_images.oci_platform("linux", "aarch64") == "linux/arm64"


@pytest.mark.parametrize(
    "bad_ref",
    [
        "quay.io/minio/minio:latest",
        "quay.io/user:password@minio/minio:stable",
        "https://quay.io/minio/minio:stable",
        "evil.example/minio/minio:stable",
    ],
)
def test_rejects_unpinned_or_non_public_registry_refs(bad_ref: str) -> None:
    rendered = {"services": {name: {"image": ref} for name, ref in REFS.items()}}
    rendered["services"]["minio"]["image"] = bad_ref
    with pytest.raises(ValueError):
        probe_public_images.select_refs(rendered)


def test_initial_401_follows_anonymous_bearer_challenge_without_leaking_token() -> None:
    fake_bearer = "synthetic-bearer-secret"
    calls: list[tuple[str, dict[str, str]]] = []
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [{"platform": {"os": "linux", "architecture": "amd64"}}],
    }

    def fetch(url: str, headers: dict[str, str]) -> probe_public_images.HttpResult:
        calls.append((url, headers))
        if len(calls) == 1:
            return probe_public_images.HttpResult(
                401,
                {
                    "www-authenticate": 'Bearer realm="https://quay.io/v2/auth",service="quay.io",scope="repository:minio/minio:pull"'
                },
                b'{"errors":[{"code":"UNAUTHORIZED"}]}',
            )
        if len(calls) == 2:
            return probe_public_images.HttpResult(
                200, {}, json.dumps({"token": fake_bearer}).encode()
            )
        assert headers["Authorization"] == "Bearer " + fake_bearer
        return probe_public_images.HttpResult(
            200,
            {"docker-content-digest": "sha256:" + "a" * 64},
            json.dumps(manifest).encode(),
        )

    result = probe_public_images.probe_manifest(REFS["minio"], "linux/amd64", fetch)

    assert result == {
        "stage": "PLATFORM",
        "http_status": 200,
        "registry_error_code": None,
        "manifest_digest": "sha256:" + "a" * 64,
        "platform_supported": True,
        "anonymous_token_flow": "COMPLETED",
    }
    assert len(calls) == 3
    assert fake_bearer not in json.dumps(result)


def test_final_manifest_404_preserves_structured_error_without_credentials() -> None:
    def fetch(_url: str, _headers: dict[str, str]) -> probe_public_images.HttpResult:
        return probe_public_images.HttpResult(
            404,
            {},
            b'{"errors":[{"code":"MANIFEST_UNKNOWN","message":"synthetic-private-value"}]}',
        )

    result = probe_public_images.probe_manifest(REFS["minio"], "linux/amd64", fetch)

    assert result["stage"] == "MANIFEST"
    assert result["http_status"] == 404
    assert result["registry_error_code"] == "MANIFEST_UNKNOWN"
    assert result["manifest_digest"] == "NOT AVAILABLE"
    assert "synthetic-private-value" not in json.dumps(result)


def test_pulls_all_three_even_if_first_fails_and_keeps_variant_separate() -> None:
    pulls: list[tuple[str, str]] = []

    def pull(ref: str, variant: str) -> tuple[int, str]:
        pulls.append((ref, variant))
        if ref == REFS["minio"] and variant == "CURRENT":
            return 1, "denied: synthetic-private-value"
        return 0, ""

    def manifest(_ref: str) -> dict[str, object]:
        return {
            "stage": "PLATFORM",
            "http_status": 200,
            "registry_error_code": None,
            "manifest_digest": "sha256:" + "b" * 64,
            "platform_supported": True,
            "anonymous_token_flow": "NOT_REQUIRED",
        }

    report = probe_public_images.probe_all(REFS, "linux/amd64", pull, manifest)

    assert len(pulls) == 6
    assert report["ready_for_acceptance"] is False
    assert report["images"][0]["service"] == "minio"
    assert report["images"][0]["pulls"][0]["variant"] == "CURRENT"
    assert report["images"][0]["pulls"][0]["exit_code"] == 1
    assert report["images"][0]["pulls"][1]["variant"] == "CLEAN_CLIENT_CONFIG"
    assert "synthetic-private-value" not in json.dumps(report)
