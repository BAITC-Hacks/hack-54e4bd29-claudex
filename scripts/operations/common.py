from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

NAMESPACE = re.compile(r"^phase8-[a-z0-9][a-z0-9-]*$")


def clickhouse_verification_expression(table: str, kind: str) -> str | None:
    """Return a merge-stable semantic check for a ClickHouse object."""
    if kind == "MATERIALIZED_VIEW":
        return None
    if table == "agg_referrals_daily":
        return "sum(referrals)"
    if table == "agg_refusals_daily":
        return "sum(refusals)"
    return "count()"


def require_phase8_namespace(value: str) -> str:
    if not NAMESPACE.fullmatch(value):
        raise ValueError("namespace должен начинаться с phase8- и быть DNS-safe")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path, *, source_project: str) -> dict[str, Any]:
    artifacts: list[dict[str, object]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == "manifest.json" or "redis" in relative.lower():
            continue
        artifacts.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "format_version": 1,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "source_project": source_project,
        "redis": "NOT_APPLICABLE_NON_AUTHORITATIVE",
        "artifacts": artifacts,
    }


def verify_manifest(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        path = root / artifact["path"]
        if not path.is_file() or sha256_file(path) != artifact["sha256"]:
            raise ValueError(f"artifact checksum mismatch: {artifact['path']}")
    return manifest


def compose(project: str, *args: str, input_bytes: bytes | None = None) -> bytes:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker executable not found")
    completed = subprocess.run(  # noqa: S603 -- executable resolved, argv is not a shell
        [docker, "compose", "-p", project, *args],
        cwd=Path(__file__).resolve().parents[2],
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        error = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"docker compose command failed: {error}")
    return completed.stdout
