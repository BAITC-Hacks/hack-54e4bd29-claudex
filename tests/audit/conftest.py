"""Синтетические фикстуры для тестов Data Audit.

Реальные медицинские выгрузки в тесты не копируются ни при каких условиях.
Все фикстуры собираются кодом и содержат заведомо вымышленные значения.
"""

from __future__ import annotations

import csv
import datetime as dt
import random
from pathlib import Path

import pytest
from openpyxl import Workbook

SYNTHETIC_ORGS = ["ORG-A", "ORG-B", "ORG-C"]
SYNTHETIC_REGIONS = ["Регион А", "Регион Б"]


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    """Каталог-источник, повторяющий форму реальной выгрузки."""
    root = tmp_path / "source"
    root.mkdir()
    _write_referrals(root / "Направления")
    _write_parts(root / "Большая выгрузка")
    _write_workbook(root / "Справочник")
    return root


def _write_referrals(directory: Path) -> None:
    directory.mkdir()
    (directory / "desc.txt").write_text(
        "Синтетические направления на плановую госпитализацию.",
        encoding="utf-8",
    )
    rows = []
    start = dt.date(2024, 1, 1)
    rng = random.Random(20260913)
    for index in range(300):
        day = start + dt.timedelta(days=index % 280)
        org = SYNTHETIC_ORGS[index % len(SYNTHETIC_ORGS)]
        registered = dt.datetime.combine(day, dt.time(9, 0))
        # Срок до госпитализации намеренно растянут: фактическая дата должна
        # выходить за последний месяц регистрации, иначе тест на выбор оси
        # ряда ничего не проверяет.
        admitted = registered + dt.timedelta(days=rng.randint(1, 120))
        rows.append(
            {
                "hospitalization_code": f"11.{org}.100.{index}",
                "referring_mo": org,
                "hospital_mo": SYNTHETIC_ORGS[(index + 1) % len(SYNTHETIC_ORGS)],
                "bed_profile": "Профиль 1" if index % 2 else "Профиль 2",
                "region_in": SYNTHETIC_REGIONS[index % len(SYNTHETIC_REGIONS)],
                "registration_dt": registered.strftime("%Y-%m-%d %H:%M:%S"),
                "hospitalization_dt": admitted.strftime("%Y-%m-%d %H:%M:%S.%f"),
                "amount": -1 if index == 7 else index * 10,
                "sdu_load_date": "2026-04-30 11:46:39",
            }
        )
    # Одна строка намеренно повторяется: проверка поиска дубликатов.
    rows.append(dict(rows[0]))
    # Расхождение написания категории.
    rows[5]["region_in"] = " регион а "
    _write_csv(directory / "Направления.csv", rows)


def _write_parts(directory: Path) -> None:
    directory.mkdir()
    for part in (1, 2):
        rows = [
            {
                "id": str(part * 1000 + index),
                "vaccination_date": (
                    dt.datetime(2024, 1, 1) + dt.timedelta(days=index)
                ).strftime("%Y-%m-%d %H:%M:%S.%f"),
                "age": index % 90,
                "region": SYNTHETIC_REGIONS[index % len(SYNTHETIC_REGIONS)],
                "medicine_organization_code": SYNTHETIC_ORGS[index % 3],
                "sdu_load_date": "2026-04-30 15:21:35",
            }
            for index in range(120)
        ]
        _write_csv(directory / f"Большая выгрузка_part_00{part}_of_002.csv", rows)


def _write_workbook(directory: Path) -> None:
    directory.mkdir()
    book = Workbook()
    sheet = book.active
    sheet.title = "Справочник"
    sheet.append([])
    sheet.append(["Код", "Наименование"])
    for code in SYNTHETIC_ORGS:
        sheet.append([code, f"Организация {code}"])
    book.create_sheet("Пустой")
    book.save(directory / "Справочник.xlsx")
    book.close()


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
