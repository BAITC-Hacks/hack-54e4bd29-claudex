"""Probe the three public registry images required by browser acceptance.

The output is a strict allowlist of public references and aggregate result fields.
Docker/registry responses and credentials never leave process memory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
SERVICES = {
    "minio": "quay.io/minio/minio",
    "minio-init": "quay.io/minio/mc",
    "keycloak": "quay.io/keycloak/keycloak",
}
TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
KNOWN_CODES = frozenset(
    {"DENIED", "UNAUTHORIZED", "MANIFEST_UNKNOWN", "TOOMANYREQUESTS", "BLOB_UNKNOWN"}
)


@dataclass(frozen=True)
class HttpResult:
    status: int | None
    headers: dict[str, str]
    body: bytes


def select_refs(config: dict[str, Any]) -> dict[str, str]:
    """Take exact public image references from rendered Compose, never from guesses."""
    services = config.get("services")
    if not isinstance(services, dict):
        raise ValueError("Rendered Compose services unavailable")
    refs: dict[str, str] = {}
    for service, repository in SERVICES.items():
        definition = services.get(service)
        image = definition.get("image") if isinstance(definition, dict) else None
        prefix = repository + ":"
        if not isinstance(image, str) or not image.startswith(prefix):
            raise ValueError("Required public image reference unavailable")
        tag = image[len(prefix) :]
        if TAG.fullmatch(tag) is None or tag.lower() == "latest":
            raise ValueError("Required public image has no fixed tag")
        refs[service] = image
    return refs


def oci_platform(os_name: str, architecture: str) -> str:
    """Translate Docker daemon architecture names to OCI platform names."""
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(architecture, architecture)
    return os_name + "/" + arch


def _registry_code(body: bytes) -> str | None:
    try:
        payload = json.loads(body[:65536])
        errors = payload.get("errors") if isinstance(payload, dict) else None
        code = errors[0].get("code") if isinstance(errors, list) and errors else None
    except (ValueError, AttributeError, TypeError):
        return None
    return code if isinstance(code, str) and code in KNOWN_CODES else None


def _token_challenge(header: str, repository: str) -> str | None:
    if not header.lower().startswith("bearer "):
        return None
    fields = dict(re.findall(r'(\w+)="([^"]*)"', header[7:]))
    realm = fields.get("realm", "")
    parsed = urlsplit(realm)
    if parsed.scheme != "https" or parsed.hostname != "quay.io" or parsed.username:
        return None
    scope = fields.get("scope", f"repository:{repository}:pull")
    if scope != f"repository:{repository}:pull":
        return None
    return (
        realm
        + "?"
        + urlencode({"service": fields.get("service", "quay.io"), "scope": scope})
    )


def _http_get(url: str, headers: dict[str, str]) -> HttpResult:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "quay.io" or parsed.username:
        return HttpResult(None, {}, b"")
    request = Request(  # noqa: S310 — HTTPS and Quay host validated above
        url, headers={**headers, "User-Agent": "MedSignal-CI-registry-probe"}
    )
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 — fixed HTTPS Quay URL
            return HttpResult(
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                response.read(2_000_000),
            )
    except HTTPError as exc:
        return HttpResult(
            exc.code,
            {key.lower(): value for key, value in exc.headers.items()},
            exc.read(65536),
        )
    except (URLError, OSError):
        return HttpResult(None, {}, b"")


def probe_manifest(
    image_ref: str,
    platform: str,
    fetch: Callable[[str, dict[str, str]], HttpResult] = _http_get,
) -> dict[str, Any]:
    """Follow Quay's standard anonymous Bearer flow and inspect the exact tag."""
    repository, tag = image_ref.removeprefix("quay.io/").rsplit(":", 1)
    url = f"https://quay.io/v2/{repository}/manifests/{tag}"
    headers = {"Accept": ACCEPT}
    response = fetch(url, headers)
    flow_state = "NOT_REQUIRED"
    if response.status == 401:
        challenge_url = _token_challenge(
            response.headers.get("www-authenticate", ""), repository
        )
        flow_state = "FAILED"
        if challenge_url is None:
            return {
                "stage": "TOKEN",
                "http_status": 401,
                "registry_error_code": _registry_code(response.body),
                "manifest_digest": "NOT AVAILABLE",
                "platform_supported": None,
                "anonymous_token_flow": flow_state,
            }
        token_response = fetch(challenge_url, {})
        try:
            payload = json.loads(token_response.body)
            token = payload.get("token") or payload.get("access_token")
        except (ValueError, AttributeError):
            token = None
        if token_response.status != 200 or not isinstance(token, str) or not token:
            return {
                "stage": "TOKEN",
                "http_status": token_response.status,
                "registry_error_code": _registry_code(token_response.body),
                "manifest_digest": "NOT AVAILABLE",
                "platform_supported": None,
                "anonymous_token_flow": flow_state,
            }
        response = fetch(url, {**headers, "Authorization": "Bearer " + token})
        flow_state = "COMPLETED"
    if response.status != 200:
        return {
            "stage": "MANIFEST" if response.status is not None else "NETWORK",
            "http_status": response.status,
            "registry_error_code": _registry_code(response.body),
            "manifest_digest": "NOT AVAILABLE",
            "platform_supported": None,
            "anonymous_token_flow": flow_state,
        }
    digest = response.headers.get("docker-content-digest", "")
    try:
        payload = json.loads(response.body)
        entries = payload.get("manifests")
        supported = (
            any(
                isinstance(entry, dict)
                and isinstance(entry.get("platform"), dict)
                and entry["platform"].get("os") == platform.partition("/")[0]
                and entry["platform"].get("architecture") == platform.partition("/")[2]
                for entry in entries
            )
            if isinstance(entries, list)
            else None
        )
    except (ValueError, AttributeError, TypeError):
        supported = None
    return {
        "stage": "PLATFORM" if supported is not None else "MANIFEST",
        "http_status": 200,
        "registry_error_code": None,
        "manifest_digest": digest if DIGEST.fullmatch(digest) else "NOT AVAILABLE",
        "platform_supported": supported,
        "anonymous_token_flow": flow_state,
    }


def _pull_result(variant: str, exit_code: int, stderr: str) -> dict[str, Any]:
    lowered = stderr.lower()
    stage = "UNKNOWN"
    for candidate, markers in (
        ("TOKEN", ("token", "authentication required")),
        ("MANIFEST", ("manifest", "repository does not exist")),
        ("PLATFORM", ("no matching manifest", "platform")),
        ("LAYERS", ("blob", "layer", "failed to copy")),
    ):
        if any(marker in lowered for marker in markers):
            stage = candidate
            break
    status_match = re.search(r"(?:status code|http|status):?\s*([45][0-9]{2})\b", lowered)
    code = next((word for word in KNOWN_CODES if word.lower() in lowered), None)
    if code is None and "denied" in lowered:
        code = "DENIED"
    return {
        "variant": variant,
        "exit_code": exit_code,
        "stage": stage if exit_code else "COMPLETE",
        "http_status": int(status_match.group(1)) if status_match else None,
        "registry_error_code": code,
    }


def probe_all(
    refs: dict[str, str],
    platform: str,
    pull: Callable[[str, str], tuple[int, str]],
    manifest: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Probe all three independently, even after the first failed pull."""
    images: list[dict[str, Any]] = []
    ready = True
    for service, image_ref in refs.items():
        manifest_result = manifest(image_ref)
        variants = [
            _pull_result(variant, *pull(image_ref, variant))
            for variant in ("CURRENT", "CLEAN_CLIENT_CONFIG")
        ]
        images.append(
            {
                "service": service,
                "image_ref": image_ref,
                "registry": "quay.io",
                "repository": image_ref.removeprefix("quay.io/").rsplit(":", 1)[0],
                "tag": image_ref.rsplit(":", 1)[1],
                "manifest": manifest_result,
                "pulls": variants,
            }
        )
        ready = (
            ready
            and variants[0]["exit_code"] == 0
            and manifest_result.get("platform_supported") is not False
        )
    return {
        "probe_version": 1,
        "runner_platform": platform,
        "same_daemon_context": True,
        "images": images,
        "ready_for_acceptance": ready,
    }


def _docker(
    command: list[str], docker_config: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if docker_config is not None:
        env["DOCKER_CONFIG"] = str(docker_config)
        env.pop("DOCKER_AUTH_CONFIG", None)
        env.pop("REGISTRY_AUTH_FILE", None)
    return subprocess.run(  # noqa: S603 — fixed Docker CLI argv, no shell
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _daemon_identity(docker_config: Path | None) -> tuple[str, str, str] | None:
    info = _docker(
        ["docker", "info", "--format", "{{.ID}}|{{.OSType}}|{{.Architecture}}"],
        docker_config,
    )
    context = _docker(["docker", "context", "show"], docker_config)
    endpoint = _docker(
        ["docker", "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
        docker_config,
    )
    if any(item.returncode for item in (info, context, endpoint)):
        return None
    return info.stdout.strip(), context.stdout.strip(), endpoint.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT / "tmp" / "acceptance"):
        print("Registry probe: invalid output location", file=sys.stderr)
        return 1
    try:
        rendered = _docker(
            [
                "docker",
                "compose",
                "--env-file",
                ".env.example",
                "config",
                "--format",
                "json",
            ]
        )
        if rendered.returncode:
            raise ValueError("Rendered Compose unavailable")
        refs = select_refs(json.loads(rendered.stdout))
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="phase8-registry-", dir=ROOT / "tmp"
        ) as temp:
            clean_config = Path(temp)
            (clean_config / "config.json").write_text("{}\n", encoding="utf-8")
            current = _daemon_identity(None)
            clean = _daemon_identity(clean_config)
            if current is None or clean is None or current != clean:
                raise ValueError("Docker daemon/context mismatch")
            parts = current[0].split("|")
            if len(parts) != 3 or not parts[0] or not parts[1] or not parts[2]:
                raise ValueError("Docker platform unavailable")
            platform = oci_platform(parts[1], parts[2])

            def pull(ref: str, variant: str) -> tuple[int, str]:
                config = clean_config if variant == "CLEAN_CLIENT_CONFIG" else None
                try:
                    result = _docker(["docker", "pull", "--quiet", ref], config)
                    return result.returncode, result.stderr
                except (OSError, subprocess.TimeoutExpired):
                    return 124, "timeout"

            report = probe_all(
                refs, platform, pull, lambda ref: probe_manifest(ref, platform)
            )
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("Registry probe: " + ("PASS" if report["ready_for_acceptance"] else "FAIL"))
        return 0 if report["ready_for_acceptance"] else 1
    except (OSError, ValueError, subprocess.TimeoutExpired, TypeError):
        print("Registry probe: FAIL (sanitized diagnostic unavailable)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
