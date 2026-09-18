"""Restore a backup into phase8-namespaced targets and verify record counts."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path
from typing import Any

from scripts.operations.common import (
    clickhouse_verification_expression,
    compose,
    require_phase8_namespace,
    verify_manifest,
)

TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_materialized_view(ddl: str) -> bool:
    return "CREATE MATERIALIZED VIEW" in ddl.upper()


def _safe_database(namespace: str, suffix: str) -> str:
    return f"{namespace.replace('-', '_')}_{suffix}"


def _clickhouse(project: str, query: str, input_bytes: bytes | None = None) -> bytes:
    command = (
        'clickhouse-client --user "$CLICKHOUSE_USER" '
        '--password "$CLICKHOUSE_PASSWORD" '
        f"--query {shlex.quote(query)}"
    )
    return compose(
        project, "exec", "-T", "clickhouse", "sh", "-c", command, input_bytes=input_bytes
    )


def restore_and_verify(backup: Path, namespace: str, project: str) -> dict[str, Any]:
    namespace = require_phase8_namespace(namespace)
    backup = backup.resolve()
    verify_manifest(backup)
    stores = json.loads((backup / "stores.json").read_text(encoding="utf-8"))

    postgres_db = _safe_database(namespace, "postgres")
    create_database = (
        'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 '
        f'-c "CREATE DATABASE {postgres_db}"'
    )
    compose(
        project,
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        create_database,
    )
    compose(
        project,
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        f'pg_restore -U "$POSTGRES_USER" -d {postgres_db} --exit-on-error',
        input_bytes=(backup / "postgres.dump").read_bytes(),
    )
    pg_count_query = shlex.quote(
        "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
    )
    pg_tables = int(
        compose(
            project,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            f'psql -U "$POSTGRES_USER" -d {postgres_db} -Atc {pg_count_query}',
        )
        .decode()
        .strip()
    )

    clickhouse_db = _safe_database(namespace, "clickhouse")
    _clickhouse(project, f"CREATE DATABASE `{clickhouse_db}`")
    source_db = stores["clickhouse_database"]
    definitions: dict[str, str] = {}
    for table in stores["clickhouse_tables"]:
        if not TABLE.fullmatch(table):
            raise ValueError(f"unsafe ClickHouse table name: {table!r}")
        ddl = (backup / "clickhouse" / f"{table}.sql").read_text(encoding="utf-8")
        definitions[table] = ddl.replace(
            f"`{source_db}`.", f"`{clickhouse_db}`."
        ).replace(f"{source_db}.", f"{clickhouse_db}.")

    # Views are triggers over their source tables. Creating them before the
    # fact restore would replay all imported facts into aggregate targets and
    # double data when those targets are restored from their own backup.
    for table, ddl in definitions.items():
        if _is_materialized_view(ddl):
            continue
        _clickhouse(project, ddl)
        native = (backup / "clickhouse" / f"{table}.native").read_bytes()
        if native:
            _clickhouse(
                project,
                f"INSERT INTO `{clickhouse_db}`.`{table}` FORMAT Native",
                input_bytes=native,
            )

    for ddl in definitions.values():
        if _is_materialized_view(ddl):
            _clickhouse(project, ddl)

    clickhouse_counts: dict[str, int] = {}
    expected_checks = stores.get("clickhouse_checks", {})
    verification: dict[str, dict[str, object]] = {}
    for table in stores["clickhouse_tables"]:
        count = _clickhouse(
            project,
            f"SELECT count() FROM `{clickhouse_db}`.`{table}` FORMAT TSVRaw",  # noqa: S608
        )
        clickhouse_counts[table] = int(count.decode().strip())
        kind = stores.get("clickhouse_kinds", {}).get(table, "TABLE")
        expression = clickhouse_verification_expression(table, kind)
        if expression is None or table not in expected_checks:
            continue
        expected = expected_checks[table]
        actual = int(
            _clickhouse(
                project,
                f"SELECT {expression} FROM `{clickhouse_db}`.`{table}` FORMAT TSVRaw",  # noqa: S608 -- allowlisted
            )
            .decode()
            .strip()
        )
        verification[table] = {"expression": expression, "value": actual}
        if actual != int(expected["value"]):
            raise RuntimeError(
                f"ClickHouse restore verification mismatch for {table}: "
                f"expected {expected['value']}, got {actual}"
            )

    minio_prefix = namespace
    mount = f"{(backup / 'minio').resolve()}:/backup:ro"
    minio_script_parts = [
        "mc alias set target http://minio:9000 "
        '"$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null'
    ]
    for bucket in stores["minio_buckets"]:
        target = f"{minio_prefix}-{bucket.removeprefix('medsignal-')}"
        minio_script_parts.extend(
            [
                f"mc mb --ignore-existing target/{target} >/dev/null",
                f"mc anonymous set none target/{target} >/dev/null",
                f"if [ -d /backup/{bucket} ]; then "
                f"mc mirror --overwrite /backup/{bucket} target/{target} >/dev/null; fi",
            ]
        )
    compose(
        project,
        "run",
        "--rm",
        "--no-deps",
        "--volume",
        mount,
        "--entrypoint",
        "/bin/sh",
        "minio-init",
        "-c",
        "; ".join(minio_script_parts),
    )

    return {
        "status": "RESTORE_VERIFIED",
        "namespace": namespace,
        "project": project,
        "postgres": {"database": postgres_db, "tables": pg_tables},
        "clickhouse": {
            "database": clickhouse_db,
            "rows": clickhouse_counts,
            "verification": verification,
        },
        "minio": {"bucket_prefix": minio_prefix, "buckets": len(stores["minio_buckets"])},
        "redis": "NOT_APPLICABLE_NON_AUTHORITATIVE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--project", default="medsignal")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    result = restore_and_verify(args.backup, args.namespace, args.project)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
