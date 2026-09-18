"""Create portable backups of the three authoritative persistent stores."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path

from scripts.operations.common import (
    build_manifest,
    clickhouse_verification_expression,
    compose,
)

TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MINIO_BUCKETS = (
    "medsignal-imports",
    "medsignal-models",
    "medsignal-exports",
    "medsignal-reports",
    "medsignal-raw",
    "medsignal-quarantine",
    "medsignal-quality",
    "medsignal-artifacts",
)


def _clickhouse(project: str, query: str) -> bytes:
    command = (
        'clickhouse-client --user "$CLICKHOUSE_USER" '
        '--password "$CLICKHOUSE_PASSWORD" --database "$CLICKHOUSE_DB" '
        f"--query {shlex.quote(query)}"
    )
    return compose(project, "exec", "-T", "clickhouse", "sh", "-c", command)


def create_backup(output: Path, project: str) -> dict[str, object]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    postgres = compose(
        project,
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom',
    )
    (output / "postgres.dump").write_bytes(postgres)

    clickhouse_dir = output / "clickhouse"
    clickhouse_dir.mkdir()
    database = (
        _clickhouse(project, "SELECT currentDatabase() FORMAT TSVRaw").decode().strip()
    )
    tables = [
        item
        for item in _clickhouse(project, "SHOW TABLES FORMAT TSVRaw")
        .decode()
        .splitlines()
        if item
    ]
    clickhouse_counts: dict[str, int] = {}
    clickhouse_kinds: dict[str, str] = {}
    clickhouse_checks: dict[str, dict[str, object]] = {}
    for table in tables:
        if not TABLE.fullmatch(table):
            raise ValueError(f"unsafe ClickHouse table name: {table!r}")
        ddl = _clickhouse(project, f"SHOW CREATE TABLE `{table}` FORMAT TSVRaw")
        is_materialized_view = b"CREATE MATERIALIZED VIEW" in ddl.upper()
        clickhouse_kinds[table] = "MATERIALIZED_VIEW" if is_materialized_view else "TABLE"
        clickhouse_counts[table] = int(
            _clickhouse(
                project,
                f"SELECT count() FROM `{table}` FORMAT TSVRaw",  # noqa: S608 -- allowlisted
            )
            .decode()
            .strip()
        )
        expression = clickhouse_verification_expression(table, clickhouse_kinds[table])
        if expression is not None:
            value = int(
                _clickhouse(
                    project,
                    f"SELECT {expression} FROM `{table}` FORMAT TSVRaw",  # noqa: S608 -- allowlisted
                )
                .decode()
                .strip()
            )
            clickhouse_checks[table] = {"expression": expression, "value": value}
        # A materialized view has no independent state. Selecting and later
        # inserting its result would replay data into the target table.
        data = (
            b""
            if is_materialized_view
            else _clickhouse(
                project,
                f"SELECT * FROM `{table}` FORMAT Native",  # noqa: S608 -- allowlisted
            )
        )
        (clickhouse_dir / f"{table}.sql").write_bytes(ddl)
        (clickhouse_dir / f"{table}.native").write_bytes(data)

    minio_dir = output / "minio"
    minio_dir.mkdir()
    for bucket in MINIO_BUCKETS:
        (minio_dir / bucket).mkdir()
    mount = f"{minio_dir}:/backup"
    buckets = " ".join(MINIO_BUCKETS)
    minio_script = (
        'mc alias set source http://minio:9000 "$MINIO_ROOT_USER" '
        '"$MINIO_ROOT_PASSWORD" >/dev/null; '
        f"for bucket in {buckets}; do "
        'mc mirror --overwrite "source/$bucket" "/backup/$bucket" >/dev/null; '
        "done"
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
        minio_script,
    )

    metadata = {
        "clickhouse_database": database,
        "clickhouse_tables": tables,
        "clickhouse_counts": clickhouse_counts,
        "clickhouse_kinds": clickhouse_kinds,
        "clickhouse_checks": clickhouse_checks,
        "minio_buckets": list(MINIO_BUCKETS),
    }
    (output / "stores.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = build_manifest(output, source_project=project)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", default="medsignal")
    args = parser.parse_args()
    manifest = create_backup(args.output, args.project)
    print(
        json.dumps({"status": "BACKUP_CREATED", "artifacts": len(manifest["artifacts"])})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
