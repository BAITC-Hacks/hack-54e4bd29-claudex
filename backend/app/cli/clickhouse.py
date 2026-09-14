"""Применение схем ClickHouse.

Запуск:
    python -m app.cli.clickhouse migrate
    python -m app.cli.clickhouse status

Отдельная команда, а не часть миграций PostgreSQL: Alembic рассчитан
на транзакционный DDL, которого в ClickHouse нет, и смешивание двух
механизмов сделало бы непонятным, что именно откатывается при сбое.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from data_pipeline.loading.clickhouse_migrations import (
    MIGRATIONS_TABLE,
    applied_versions,
    apply_all,
    ensure_migrations_table,
    load_migrations,
)

from app.core.config import load_settings_or_exit
from app.database.clickhouse import get_client

DEFAULT_DIRECTORY = Path("/opt/medsignal/database/clickhouse/migrations")
EXIT_OK = 0
EXIT_FAILED = 1


def _directory(raw: str | None) -> Path:
    if raw:
        return Path(raw)
    if DEFAULT_DIRECTORY.is_dir():
        return DEFAULT_DIRECTORY
    return Path(__file__).resolve().parents[3] / "database" / "clickhouse" / "migrations"


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    load_settings_or_exit()

    parser = argparse.ArgumentParser(
        prog="app.cli.clickhouse",
        description="Версионированные схемы аналитического хранилища",
    )
    parser.add_argument("command", choices=("migrate", "status"))
    parser.add_argument("--directory", default=None)
    args = parser.parse_args(argv)

    directory = _directory(args.directory)
    if not directory.is_dir():
        print(f"[medsignal] Каталог миграций не найден: {directory}", file=sys.stderr)
        return EXIT_FAILED

    client = get_client()

    if args.command == "status":
        ensure_migrations_table(client)
        known = applied_versions(client)
        for migration in load_migrations(directory):
            state = "применена" if migration.version in known else "не применена"
            print(f"{migration.version:<6} {migration.name:<28} {state}")
        print(f"\nТаблица версий: {MIGRATIONS_TABLE}")
        return EXIT_OK

    for outcome in apply_all(client, directory):
        if outcome.applied:
            print(
                f"[medsignal] {outcome.version} {outcome.name}: "
                f"применено команд {outcome.statements}"
            )
        else:
            print(f"[medsignal] {outcome.version} {outcome.name}: уже применена")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
