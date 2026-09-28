from __future__ import annotations

import hashlib
import json
import re
import shlex
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
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    listed = set()
    for artifact in manifest["artifacts"]:
        relative = artifact["path"]
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or relative in listed:
            raise ValueError("invalid manifest artifact path")
        listed.add(relative)
        if not path.is_file() or sha256_file(path) != artifact["sha256"]:
            raise ValueError("artifact checksum mismatch in manifest")
    # Legacy Redis exclusions remain readable; authoritative restore inputs
    # cannot silently bypass integrity checking by being absent from the manifest.
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path != root / "manifest.json"
        and "redis" not in path.relative_to(root).as_posix().lower()
    }
    if actual != listed:
        raise ValueError("manifest artifact inventory mismatch")
    return manifest


def postgres_inventory(project: str, database: str | None = None) -> dict[str, Any]:
    """Aggregate rows, constraints and revision only; never return patient values.

    One repeatable-read transaction makes this inventory internally consistent.
    Backup callers must quiesce writers for cross-store/dump consistency.
    """
    query = r"""
BEGIN ISOLATION LEVEL REPEATABLE READ;
SET LOCAL statement_timeout = '30s';
CREATE TEMP TABLE recovery_inventory (payload jsonb);
DO $body$
DECLARE item record; n bigint; counts jsonb := '{}'::jsonb;
        constraints jsonb := '[]'::jsonb; versions jsonb := '[]'::jsonb;
        definition text;
BEGIN
  FOR item IN SELECT tablename FROM pg_tables
              WHERE schemaname = 'public' ORDER BY tablename LOOP
    EXECUTE format('SELECT count(*) FROM public.%I', item.tablename) INTO n;
    counts := counts || jsonb_build_object(item.tablename, n);
  END LOOP;
  FOR item IN SELECT c.relname, k.conname, k.contype, k.convalidated,
                     pg_get_constraintdef(k.oid) AS definition
    FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
    JOIN pg_namespace ns ON ns.oid = c.relnamespace WHERE ns.nspname = 'public'
    ORDER BY c.relname, k.conname LOOP
    definition := item.definition;
    IF item.contype = 'c' THEN
      -- pg_dump/restore can move an array cast onto its elements. Reparse
      -- CHECK DDL on an empty temporary table for stable server semantics;
      -- retain all casts, constraint names and original validation flags.
      EXECUTE format(
        'CREATE TEMP TABLE recovery_constraint_normalization (LIKE public.%I)',
        item.relname);
      EXECUTE format(
        'ALTER TABLE pg_temp.recovery_constraint_normalization '
        'ADD CONSTRAINT recovery_check %s', definition);
      SELECT pg_get_constraintdef(oid) INTO definition FROM pg_constraint
        WHERE conrelid = 'pg_temp.recovery_constraint_normalization'::regclass
          AND conname = 'recovery_check';
      DROP TABLE pg_temp.recovery_constraint_normalization;
    END IF;
    constraints := constraints || jsonb_build_array(jsonb_build_object(
      'table', item.relname, 'name', item.conname,
      'definition', definition, 'validated', item.convalidated));
  END LOOP;
  IF to_regclass('public.alembic_version') IS NOT NULL THEN
    SELECT coalesce(jsonb_agg(version_num ORDER BY version_num), '[]'::jsonb)
      INTO versions FROM public.alembic_version;
  END IF;
  INSERT INTO recovery_inventory VALUES (jsonb_build_object(
      'tables', counts, 'constraints', constraints, 'alembic_versions', versions));
END $body$;
SELECT payload FROM recovery_inventory;
ROLLBACK;
"""
    target = shlex.quote(database) if database else '"$POSTGRES_DB"'
    command = 'psql -X -qAt -U "$POSTGRES_USER" -d ' + target + " -v ON_ERROR_STOP=1"
    raw = compose(
        project, "exec", "-T", "postgres", "sh", "-c", command, input_bytes=query.encode()
    )
    return json.loads(raw)


def verify_postgres_inventory(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    required = {"tables", "constraints", "alembic_versions"}
    if (
        not required.issubset(expected)
        or not required.issubset(actual)
        or expected != actual
    ):
        raise RuntimeError("PostgreSQL restore content/constraint/revision mismatch")


def object_inventory(root: Path, buckets: list[str] | tuple[str, ...]) -> dict[str, Any]:
    inventory = {}
    for bucket in buckets:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", bucket):
            raise ValueError("unsafe MinIO bucket")
        directory = root / bucket
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError("missing or unsafe MinIO bucket directory")
        objects = {}
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError("unsafe MinIO object path")
            if path.is_file():
                objects[path.relative_to(directory).as_posix()] = {
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
        inventory[bucket] = objects
    return inventory


def verify_object_inventory(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    if expected != actual:
        # Neither object keys nor contents belong in application logs.
        raise RuntimeError("MinIO restored object inventory/hash mismatch")


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
