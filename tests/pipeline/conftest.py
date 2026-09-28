"""Синтетические фикстуры конвейера загрузки.

Реальные медицинские выгрузки в тесты не попадают ни при каких условиях.
Все значения здесь вымышлены: наименования организаций условны, коды
случаев собраны из чисел, диагнозы взяты из общедоступного справочника
МКБ-10 как коды, а не как сведения о людях.
"""

from __future__ import annotations

import csv
import datetime as dt
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from data_pipeline.contracts import DatasetContract, get_contract
from data_pipeline.privacy.pseudonymization import Pseudonymizer

TEST_KEY = "test-pseudonymization-key-0123456789abcdef"
SECOND_KEY = "another-pseudonymization-key-0123456789ab"

ORG_A = 'Государственное предприятие "Больница А"'
ORG_B = 'Товарищество с ограниченной ответственностью "Клиника Б"'
MO_CODE_A = "01A1"
MO_CODE_B = "02B2"
LOAD_STAMP = "2026-05-01 03:00:00.000000"


@pytest.fixture
def pseudonymizer() -> Pseudonymizer:
    return Pseudonymizer.from_secret(TEST_KEY)


@pytest.fixture
def import_id() -> uuid.UUID:
    return uuid.UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture
def now() -> dt.datetime:
    return dt.datetime(2026, 5, 1, 12, 0, 0)


# ---------------------------------------------------------------------------
# Запись файлов выгрузок
# ---------------------------------------------------------------------------


def write_csv(path: Path, rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in columns})
    return path


def dataset_file(
    root: Path,
    contract: DatasetContract,
    rows: Sequence[dict[str, Any]],
    name: str | None = None,
) -> Path:
    directory = root / contract.source_directory
    file_name = name or f"{contract.source_directory}.csv"
    return write_csv(directory / file_name, rows, contract.column_names)


def referral_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "hospitalization_code": "61.01W9.321.72S",
        "referring_mo": ORG_A,
        "hospital_mo": ORG_B,
        "icd10_ref_diag_code": "J41.0",
        "diagnosis_name": "Простой хронический бронхит",
        "bed_profile": "Неврологические для взрослых",
        "registration_dt": "2025-01-16 16:01:14.463000",
        "planned_dt": "2025-01-20 00:00:00",
        "polyclinic_dt": "2025-01-16 16:01:18.910000",
        "hospitalization_dt": "2025-01-21 10:18:00",
        "refusal_dt": "",
        "territorial_type": "Город",
        "referral_purpose": "Консервативное лечение",
        "finance_source": "Активы Фонда на ОСМС",
        "sdu_load_date": LOAD_STAMP,
    }
    row.update(overrides)
    return row


def waiting_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "region_origin_code": "11",
        "mo_destination_code": MO_CODE_A,
        "profile_code": "321",
        "patient_seq_no": "172",
        "icd10_ref_diag_code": "Q80.0",
        "diagnosis_name": "Врожденный ихтиоз простой",
        "operation_code": "12345",
        "operation_name": "Условная операция",
        "registration_dt": "2025-02-24 10:43:28.457000",
        "planned_dt": "2025-03-05 00:00:00",
        "sdu_load_date": LOAD_STAMP,
    }
    row.update(overrides)
    return row


def refusal_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "region_in": "Регион А",
        "org_in": ORG_A,
        "resident": "Город",
        "insured": "Застрахован",
        "benefit_cat": "Нет льгот",
        "refuse_dt": "2025-01-18 12:21:00",
        "attach_region": "Регион А",
        "attach_org": ORG_B,
        "icd10": "J06.9",
        "icd_name": "Острая инфекция верхних дыхательных путей",
        "amount": "2153.82",
        "finance_src": "Активы Фонда на ОСМС",
        "sdu_load_date": LOAD_STAMP,
    }
    row.update(overrides)
    return row


def treated_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "medicine_organization": ORG_A,
        "discharged_total": "367",
        "discharged_children": "1",
        "treated_budget": "366",
        "treated_paid": "1",
        "discharged_within_day": "0",
        "deaths_total": "0",
        "bed_days": "1846",
        "amount_to_pay": "38857850.45",
        "sdu_load_date": LOAD_STAMP,
    }
    row.update(overrides)
    return row


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    """Каталог источника с минимально достаточными выгрузками."""
    root = tmp_path / "source"
    dataset_file(root, get_contract("REFERRALS"), [referral_row()])
    dataset_file(root, get_contract("WAITING"), [waiting_row()])
    dataset_file(root, get_contract("REFUSALS"), [refusal_row()])
    dataset_file(root, get_contract("TREATED"), [treated_row()])
    return root


# ---------------------------------------------------------------------------
# Подставные внешние системы
# ---------------------------------------------------------------------------


class FakeQueryResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.result_rows = rows


class FakeClickHouse:
    """Подставной ClickHouse: хранит вставленные строки в памяти.

    Моделируется ровно то, от чего зависит загрузчик: вставка, счёт строк
    по импорту, перенос из промежуточной таблицы и сброс раздела. Больше
    не нужно, а настоящая проверка схемы выполняется интеграционным
    тестом против работающего ClickHouse.
    """

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.commands: list[str] = []

    def insert(self, table: str, data: Any, column_names: Any = None, **_: Any) -> None:
        rows = self.tables.setdefault(table, [])
        for values in data:
            rows.append(dict(zip(column_names, values, strict=True)))

    def query(self, query: str, parameters: Any = None) -> FakeQueryResult:
        table = query.split(" FROM ")[1].split(" ")[0]
        import_id = str((parameters or {}).get("import_id", ""))
        rows = self.tables.get(table, [])
        count = sum(1 for row in rows if str(row.get("import_id")) == import_id)
        return FakeQueryResult([(count,)])

    def command(self, cmd: str, parameters: Any = None) -> None:
        self.commands.append(cmd)
        import_id = str((parameters or {}).get("import_id", ""))

        if cmd.startswith("INSERT INTO"):
            target = cmd.split("INSERT INTO ")[1].split(" ")[0]
            source = cmd.split(" FROM ")[1].split(" ")[0]
            moved = [
                dict(row)
                for row in self.tables.get(source, [])
                if str(row.get("import_id")) == import_id
            ]
            self.tables.setdefault(target, []).extend(moved)
            return

        if "DROP PARTITION" in cmd:
            table = cmd.split("ALTER TABLE ")[1].split(" ")[0]
            self.tables[table] = [
                row
                for row in self.tables.get(table, [])
                if str(row.get("import_id")) != import_id
            ]
            return

        if "DELETE WHERE" in cmd:
            table = cmd.split("ALTER TABLE ")[1].split(" ")[0]
            self.tables[table] = [
                row
                for row in self.tables.get(table, [])
                if str(row.get("import_id")) != import_id
            ]

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables.get(table, [])

    def frame(self, table: str) -> pl.DataFrame:
        return pl.DataFrame(self.tables.get(table, []))


class FakeObjectStore:
    """Подставное объектное хранилище карантина."""

    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}

    def ensure_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def put(self, bucket: str, key: str, data: Any, size: int, content_type: str) -> None:  # noqa: ARG002
        self.objects[(bucket, key)] = data.read()

    def get(self, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]


@pytest.fixture
def clickhouse() -> FakeClickHouse:
    return FakeClickHouse()


@pytest.fixture
def object_store() -> FakeObjectStore:
    return FakeObjectStore()
