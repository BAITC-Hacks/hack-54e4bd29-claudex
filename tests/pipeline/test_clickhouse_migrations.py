"""Применение версионированных схем ClickHouse."""

from __future__ import annotations

from pathlib import Path

import pytest

from data_pipeline.loading.clickhouse_migrations import (
    MIGRATIONS_TABLE,
    DestructiveMigrationError,
    apply_all,
    load_migrations,
    split_statements,
)

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "database" / "clickhouse" / "migrations"
)


class FakeResult:
    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self.result_rows = rows


class FakeClient:
    def __init__(self, applied: dict[str, str] | None = None) -> None:
        self.commands: list[str] = []
        self.applied = applied or {}

    def command(self, cmd: str, parameters: dict | None = None) -> None:
        self.commands.append(cmd)
        if cmd.startswith("INSERT INTO") and parameters:
            self.applied[parameters["version"]] = parameters["checksum"]

    def query(self, query: str, parameters: dict | None = None) -> FakeResult:  # noqa: ARG002
        return FakeResult(list(self.applied.items()))


# --- Разбор SQL -------------------------------------------------------------


def test_semicolon_inside_a_string_does_not_split_the_statement() -> None:
    """Комментарий к столбцу может содержать точку с запятой."""
    sql = "CREATE TABLE t (a String COMMENT 'псевдоним; код не хранится');"
    statements = split_statements(sql)
    assert len(statements) == 1
    assert "код не хранится" in statements[0]


def test_double_quote_inside_a_string_is_an_escape() -> None:
    sql = "SELECT 'a''b; c' AS x;"
    assert split_statements(sql) == ["SELECT 'a''b; c' AS x"]


def test_line_comment_is_removed() -> None:
    sql = "-- пояснение\nSELECT 1;"
    assert split_statements(sql) == ["SELECT 1"]


def test_double_dash_inside_a_string_is_not_a_comment() -> None:
    sql = "SELECT 'код--значение' AS x;"
    assert split_statements(sql) == ["SELECT 'код--значение' AS x"]


def test_block_comment_is_removed() -> None:
    sql = "/* пояснение */ SELECT 1;"
    assert split_statements(sql) == ["SELECT 1"]


# --- Защита от разрушительных команд ----------------------------------------


def test_destructive_migration_is_refused(tmp_path: Path) -> None:
    (tmp_path / "001_bad.sql").write_text("DROP TABLE facts;", encoding="utf-8")
    with pytest.raises(DestructiveMigrationError):
        load_migrations(tmp_path)


def test_word_drop_inside_a_comment_is_allowed(tmp_path: Path) -> None:
    """Объяснение, почему DROP здесь нет, не должно ломать миграцию."""
    (tmp_path / "001_ok.sql").write_text(
        "-- Никаких DROP TABLE здесь нет\nCREATE TABLE t (a String);",
        encoding="utf-8",
    )
    assert len(load_migrations(tmp_path)) == 1


# --- Реальные миграции проекта ----------------------------------------------


def test_project_migrations_load() -> None:
    migrations = load_migrations(MIGRATIONS_DIR)
    versions = [m.version for m in migrations]
    assert versions == [
        "001_fact_referral_events",
        "002_fact_waiting_events",
        "003_fact_refusal_events",
        "004_fact_treated_snapshot",
        "005_daily_aggregates",
        "006_mapping_projection",
    ]


def test_version_is_the_full_stem() -> None:
    """Версия не сталкивается с записями скриптов прежних фаз."""
    versions = {m.version for m in load_migrations(MIGRATIONS_DIR)}
    assert "001_init" not in versions
    assert "001" not in versions


def test_applying_twice_changes_nothing() -> None:
    client = FakeClient()
    first = apply_all(client, MIGRATIONS_DIR)
    assert all(outcome.applied for outcome in first)

    second = apply_all(client, MIGRATIONS_DIR)
    assert not any(outcome.applied for outcome in second)


def test_changed_migration_is_refused() -> None:
    """Принятую миграцию правят новой, а не на месте."""
    client = FakeClient(applied={"001_fact_referral_events": "другая-сумма"})
    with pytest.raises(DestructiveMigrationError):
        apply_all(client, MIGRATIONS_DIR)


def test_legacy_record_without_checksum_is_accepted() -> None:
    """Запись прежней фазы не содержит суммы и перепроверке не подлежит."""
    client = FakeClient(applied={"001_fact_referral_events": ""})
    outcomes = {o.version: o.applied for o in apply_all(client, MIGRATIONS_DIR)}
    assert outcomes["001_fact_referral_events"] is False


def test_version_table_is_extended_not_recreated() -> None:
    client = FakeClient()
    apply_all(client, MIGRATIONS_DIR)
    alters = [c for c in client.commands if "ADD COLUMN IF NOT EXISTS" in c]
    assert len(alters) == 2
    assert all(MIGRATIONS_TABLE in c for c in alters)
