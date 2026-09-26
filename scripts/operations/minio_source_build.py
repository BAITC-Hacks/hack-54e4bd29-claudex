"""Build two project-local MinIO images from pinned, signed upstream tags.

This tool is only for disposable synthetic acceptance. It never pushes images.
Command output stays in memory so registry credentials and proxy details cannot
reach CI logs or uploaded evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from scripts.operations.prepare_acceptance import DIGEST_PATTERN, validate_project_name

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "infrastructure/acceptance/minio-source-build.json"
BUILD_ROOT = ROOT / "tmp/acceptance-build"
EXPECTED = {
    "server": (
        "https://github.com/minio/minio.git",
        "RELEASE.2024-11-07T00-52-20Z",
        "bae05edea0dee78128e59013583b80a8d971c74e",
        "cefc43e4daa4cbb490ef6726ea374e26a93eb85e",
    ),
    "client": (
        "https://github.com/minio/mc.git",
        "RELEASE.2024-11-05T11-29-45Z",
        "653030740dcb89816d5320648a6b836a1a0d8e89",
        "6ac18619cf881074fe6edcc79ab62c9c85da60b9",
    ),
}
SAFE_HASH = re.compile(r"[0-9a-f]{64}")
UPSTREAM_VARIANT = "UNMODIFIED_UPSTREAM"
PATCHED_VARIANT = "PATCHED_ACCEPTANCE"
KNOWN_APPLICATION_CRITICAL = "CVE-2024-55949"
APPLICATION_ADVISORY = (
    "https://github.com/minio/minio/security/advisories/GHSA-cwq8-g58r-32hg"
)


class KnownApplicationCriticalError(RuntimeError):
    """A confirmed MinIO application vulnerability prevents acceptance use."""


def validate_build_contract(manifest: dict[str, Any]) -> None:
    """Reject a changed upstream or unpinned build contract."""
    if (
        manifest.get("platform") != "linux/amd64"
        or manifest.get("go_version") != "1.24.13"
        or manifest.get("signer_fingerprint")
        != "4405F3F0DDBA1B9E68A31D2512C74390F9AAC728"
        or manifest.get("signer_key_url") != "https://github.com/minio-trusted.gpg"
        or manifest.get("signer_key_sha256")
        != "1e0c6af3cb1bb9b7715062e0ed65f22f75fee3db303efbbf5a368dfbf2f6508a"
        or not isinstance(manifest.get("builder_image"), str)
        or not manifest["builder_image"].endswith(
            "@sha256:3641e0d9b931dc4f2f185dcd669c4679670e9277c8166a838ddb98a2d4389cb5"
        )
        or not isinstance(manifest.get("runtime_image"), str)
        or not manifest["runtime_image"].endswith(
            "@sha256:4b7ce07002c69e8f3d704a9c5d6fd3053be500b7f1c69fc0d80990c2ad8dd412"
        )
    ):
        raise ValueError("MinIO source contract changed")
    patches = manifest.get("patched_acceptance")
    if not isinstance(patches, dict) or set(patches) != set(EXPECTED):
        raise ValueError("MinIO acceptance patch contract changed")
    for name, expected in EXPECTED.items():
        item = manifest.get(name)
        if (
            not isinstance(item, dict)
            or tuple(
                item.get(field)
                for field in ("repository", "tag", "tag_object_sha", "commit_sha")
            )
            != expected
        ):
            raise ValueError("MinIO source contract changed")
        patch = patches.get(name)
        expected_path = f"infrastructure/acceptance/patches/{name}-go-mod.patch"
        if (
            not isinstance(patch, dict)
            or patch.get("path") != expected_path
            or not isinstance(patch.get("sha256"), str)
            or SAFE_HASH.fullmatch(patch["sha256"]) is None
            or hashlib.sha256((ROOT / expected_path).read_bytes()).hexdigest()
            != patch["sha256"]
        ):
            raise ValueError("MinIO acceptance patch contract changed")


def require_no_known_application_critical(manifest: dict[str, Any]) -> None:
    """Stop dependency-only builds of the vulnerable MinIO application code."""
    if manifest["server"]["commit_sha"] == EXPECTED["server"][3]:
        raise KnownApplicationCriticalError(
            f"MinIO application CRITICAL {KNOWN_APPLICATION_CRITICAL} blocks acceptance; "
            f"see {APPLICATION_ADVISORY}"
        )


def _apply_acceptance_patch(name: str, source: Path, manifest: dict[str, Any]) -> str:
    """Apply the reviewed module-only delta after signed-source verification."""
    patch = manifest["patched_acceptance"][name]
    patch_path = ROOT / patch["path"]
    _run(["git", "apply", "--check", str(patch_path)], cwd=source)
    _run(["git", "apply", str(patch_path)], cwd=source)
    changed = set(_run(["git", "diff", "--name-only"], cwd=source).splitlines())
    if changed != {"go.mod", "go.sum"}:
        raise ValueError("Acceptance patch changed files beyond Go modules")
    module = (source / "go.mod").read_text(encoding="utf-8")
    if (
        "go 1.24.0\n" not in module
        or "google.golang.org/grpc v1.79.3" not in module
        or (name == "server" and "github.com/rabbitmq/amqp091-go v1.13.0" not in module)
    ):
        raise ValueError("Acceptance patch omitted a fixed dependency")
    return patch["sha256"]


def _run(
    args: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> str:
    """Run a fixed argv command; never include its raw output in an error."""
    try:
        result = subprocess.run(  # noqa: S603 — fixed executable and validated args
            args,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Acceptance source-build command unavailable") from exc
    if result.returncode:
        raise RuntimeError("Acceptance source-build command failed")
    return result.stdout.strip()


def _trusted_key(project_dir: Path, manifest: dict[str, Any]) -> Path:
    try:
        with urlopen(manifest["signer_key_url"], timeout=30) as response:  # noqa: S310
            key = response.read(32_768)
    except OSError as exc:
        raise RuntimeError("Upstream signing key unavailable") from exc
    if hashlib.sha256(key).hexdigest() != manifest["signer_key_sha256"]:
        raise ValueError("Upstream signing key hash mismatch")
    home = project_dir / "gnupg"
    home.mkdir(mode=0o700)
    key_file = project_dir / "upstream-key.gpg"
    key_file.write_bytes(key)
    _run(["gpg", "--homedir", str(home), "--batch", "--import", str(key_file)])
    listing = _run(
        ["gpg", "--homedir", str(home), "--batch", "--with-colons", "--fingerprint"]
    )
    if f"fpr:::::::::{manifest['signer_fingerprint']}:" not in listing:
        raise ValueError("Upstream signing key fingerprint mismatch")
    return home


def _source(
    name: str, manifest: dict[str, Any], project_dir: Path, gpg_home: Path
) -> Path:
    item = manifest[name]
    source = project_dir / name
    clone_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    _run(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "clone",
            "--depth",
            "1",
            "--branch",
            item["tag"],
            "--",
            item["repository"],
            str(source),
        ],
        env=clone_env,
        timeout=900,
    )
    tag_object = _run(["git", "rev-parse", f"refs/tags/{item['tag']}"], cwd=source)
    commit = _run(["git", "rev-parse", f"refs/tags/{item['tag']}^{{commit}}"], cwd=source)
    if tag_object != item["tag_object_sha"] or commit != item["commit_sha"]:
        raise ValueError("Signed upstream tag changed")
    _run(
        ["git", "tag", "-v", item["tag"]],
        cwd=source,
        env={**clone_env, "GNUPGHOME": str(gpg_home)},
    )
    if _run(["git", "status", "--porcelain"], cwd=source):
        raise ValueError("Upstream source checkout is modified")
    return source


def _image_id(tag: str) -> str:
    value = _run(["docker", "image", "inspect", tag, "--format", "{{.Id}}"])
    if DIGEST_PATTERN.fullmatch(value) is None:
        raise ValueError("Built image has no local content ID")
    return value


def _build_one(
    name: str, project: str, item: dict[str, str], source: Path, *, patched: bool
) -> dict[str, str]:
    tag = f"{project}-minio-{name}:acceptance"
    dockerfile = ROOT / f"infrastructure/acceptance/minio-{name}.Dockerfile"
    _run(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--pull",
            "--quiet",
            "--file",
            str(dockerfile),
            "--tag",
            tag,
            "--build-arg",
            f"EXPECTED_COMMIT={item['commit_sha']}",
            "--build-arg",
            f"VERSION_TIMESTAMP={item['version_timestamp']}",
            "--build-arg",
            f"PATCH_VARIANT={'patched' if patched else 'upstream'}",
            str(source),
        ],
        timeout=3600,
    )
    image_id = _image_id(tag)
    identity = _run(
        [
            "docker",
            "image",
            "inspect",
            tag,
            "--format",
            "{{.Os}}/{{.Architecture}} {{.Config.User}}",
        ]
    )
    if identity != "linux/amd64 10001:10001":
        raise ValueError("Built image platform or runtime user mismatch")
    label = _run(
        [
            "docker",
            "image",
            "inspect",
            tag,
            "--format",
            '{{index .Config.Labels "org.medsignal.acceptance.variant"}}',
        ]
    )
    if label != ("patched" if patched else "upstream"):
        raise ValueError("Built image variant label mismatch")
    binary = "minio" if name == "server" else "mc"
    version = _run(
        ["docker", "run", "--rm", "--network", "none", tag, "--version"],
        timeout=30,
    )
    if item["tag"] not in version:
        raise ValueError("Built binary release version mismatch")
    digest_line = _run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "/bin/sh",
            tag,
            "-c",
            f"sha256sum /usr/local/bin/{binary}",
        ]
    )
    binary_hash = digest_line.split(maxsplit=1)[0]
    if SAFE_HASH.fullmatch(binary_hash) is None:
        raise ValueError("Built binary checksum unavailable")
    return {
        "tag": tag,
        "image_id": image_id,
        "binary_sha256": binary_hash,
        "reported_version": item["tag"],
        "tag_object_sha": item["tag_object_sha"],
        "commit_sha": item["commit_sha"],
    }


def build(project: str, *, patched: bool = False) -> dict[str, Any]:
    """Verify signed source and build local images in one disposable namespace."""
    validate_project_name(project)
    manifest = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    validate_build_contract(manifest)
    require_no_known_application_critical(manifest)
    project_dir = BUILD_ROOT / project
    project_dir.mkdir(parents=True, exist_ok=False)
    gpg_home = _trusted_key(project_dir, manifest)
    images: dict[str, dict[str, Any]] = {}
    for name in ("server", "client"):
        source = _source(name, manifest, project_dir, gpg_home)
        patch_sha = _apply_acceptance_patch(name, source, manifest) if patched else None
        images[name] = _build_one(name, project, manifest[name], source, patched=patched)
        images[name]["patch_sha256"] = patch_sha
        print(f"Project-built MinIO {name}: verified source, binary, local image ID")
    evidence = {
        "project": project,
        "build_contract_sha256": hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        "purpose": "isolated-synthetic-acceptance-only",
        "variant": PATCHED_VARIANT if patched else UPSTREAM_VARIANT,
        "platform": manifest["platform"],
        "go_version": manifest["go_version"],
        "builder_image": manifest["builder_image"],
        "runtime_image": manifest["runtime_image"],
        "signer_fingerprint": manifest["signer_fingerprint"],
        "source_method": "shallow Git clone of signed annotated tag",
        "source_archive_checksum": None,
        "images": images,
    }
    (project_dir / "source-images.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    return evidence


def load_built_images(project: str) -> dict[str, str]:
    """Fail closed unless both project tags still resolve to recorded local IDs."""
    validate_project_name(project)
    evidence = json.loads(
        (BUILD_ROOT / project / "source-images.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    validate_build_contract(manifest)
    require_no_known_application_critical(manifest)
    images = evidence.get("images")
    variant = evidence.get("variant")
    if (
        evidence.get("project") != project
        or variant not in (UPSTREAM_VARIANT, PATCHED_VARIANT)
        or evidence.get("build_contract_sha256")
        != hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
        or not isinstance(images, dict)
        or set(images) != set(EXPECTED)
    ):
        raise ValueError("Source image manifest does not match acceptance project")
    result: dict[str, str] = {}
    for name in EXPECTED:
        row = images[name]
        tag = f"{project}-minio-{name}:acceptance"
        if (
            not isinstance(row, dict)
            or row.get("tag") != tag
            or row.get("tag_object_sha") != EXPECTED[name][2]
            or row.get("commit_sha") != EXPECTED[name][3]
            or row.get("patch_sha256")
            != (
                manifest["patched_acceptance"][name]["sha256"]
                if variant == PATCHED_VARIANT
                else None
            )
            or not isinstance(row.get("image_id"), str)
            or DIGEST_PATTERN.fullmatch(row["image_id"]) is None
            or _image_id(tag) != row["image_id"]
        ):
            raise ValueError(
                "Source image does not match recorded ID or patch provenance"
            )
        result[name] = row["image_id"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--patched-acceptance", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "build":
            build(args.project, patched=args.patched_acceptance)
        else:
            load_built_images(args.project)
        print("Project-built MinIO source images: PASS")
        return 0
    except KnownApplicationCriticalError:
        print(
            f"MinIO source build: BLOCKED_KNOWN_APPLICATION_CRITICAL "
            f"{KNOWN_APPLICATION_CRITICAL}",
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(
            f"Project-built MinIO source images: FAIL ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
