"""Проверки качества данных.

Модуль только фиксирует найденное. Он ничего не исправляет и не нормализует:
на этапе аудита неизвестно, что из обнаруженного является ошибкой выгрузки,
а что — свойством предметной области. Решение принимает владелец данных.

Часть проверок опирается на уже собранный профиль и не требует нового
прохода по файлам. Дорогие проверки — полные дубликаты строк, дубликаты
ключей, расхождения написания категорий — выполняются отдельными проходами
и пропускаются на выгрузках, где стоимость превышает бюджет памяти.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

import polars as pl

from data_pipeline.audit.profiler import (
    SKIPPED,
    ColumnProfile,
    TableProfile,
    scan_table,
)

# Порог, выше которого столбец считается категориальным и проверяется
# на расхождения написания.
CATEGORY_MAX_CARDINALITY = 500
# Выше этого объёма дорогие проверки не выполняются.
EXPENSIVE_CHECK_LIMIT_BYTES = 1_500_000_000

# Поля, для которых семантика очевидна и отрицательное значение невозможно.
NON_NEGATIVE_HINTS = (
    "count",
    "total",
    "amount",
    "sum",
    "days",
    "age",
    "discharged",
    "treated",
    "deaths",
    "bed_days",
)


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(slots=True)
class Finding:
    dataset: str
    table: str
    column: str | None
    check: str
    severity: str
    detail: str
    affected_rows: int | None = None


@dataclass(slots=True)
class TableQuality:
    dataset: str
    table: str
    row_count: int
    duplicate_rows: int | None
    duplicate_rows_status: str
    findings: list[Finding] = field(default_factory=list)
    skipped_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["findings"] = [asdict(f) for f in self.findings]
        return payload


def _normalisation_key(expr: pl.Expr) -> pl.Expr:
    """Написания, различающиеся только регистром, пробелами и префиксом.

    «Алматы», «г. Алматы» и «АЛМАТЫ» дают один ключ. Это позволяет
    обнаружить расхождение, не изменяя сами значения.
    """
    return (
        expr.str.strip_chars()
        .str.to_lowercase()
        .str.replace_all(r"^(г\.|г |город |обл\.|область )\s*", "")
        .str.replace_all(r"[\s\.\"'«»№,()-]+", "")
    )


def _looks_non_negative(column: str) -> bool:
    lowered = column.lower()
    return any(hint in lowered for hint in NON_NEGATIVE_HINTS)


def check_table(
    profile: TableProfile,
    paths: Sequence[Path],
    key_columns: Sequence[str] = (),
) -> TableQuality:
    """Собрать замечания по качеству одной таблицы."""
    findings: list[Finding] = []
    skipped: list[str] = []
    expensive_allowed = profile.size_bytes <= EXPENSIVE_CHECK_LIMIT_BYTES

    def add(
        column: str | None,
        check: str,
        severity: Severity,
        detail: str,
        rows: int | None = None,
    ) -> None:
        findings.append(
            Finding(
                dataset=profile.dataset,
                table=profile.table,
                column=column,
                check=check,
                severity=severity.value,
                detail=detail,
                affected_rows=rows,
            )
        )

    # --- Проверки по уже собранному профилю --------------------------------
    for column in profile.columns:
        name = column.column_name

        if column.null_percentage >= 50.0:
            add(
                name,
                "MISSING VALUES",
                Severity.CRITICAL,
                f"пусто в {column.null_percentage:.1f}% строк",
                column.null_count,
            )
        elif column.null_percentage >= 5.0:
            add(
                name,
                "MISSING VALUES",
                Severity.WARNING,
                f"пусто в {column.null_percentage:.1f}% строк",
                column.null_count,
            )

        if column.empty_string_count:
            add(
                name,
                "EMPTY STRINGS",
                Severity.WARNING,
                "встречается пустая строка вместо отсутствующего значения",
                column.empty_string_count,
            )

        if column.whitespace_padded_count:
            add(
                name,
                "WHITESPACE ISSUES",
                Severity.WARNING,
                "значения содержат ведущие или завершающие пробелы",
                column.whitespace_padded_count,
            )

        if column.inferred_type == "empty":
            add(
                name,
                "EMPTY COLUMN",
                Severity.WARNING,
                "столбец не содержит ни одного непустого значения",
                profile.row_count,
            )

        if column.notes:
            for note in column.notes:
                add(name, "TYPE INCONSISTENCIES", Severity.WARNING, note)

        if column.inferred_type in {"integer", "float"}:
            minimum = float(column.min_value) if column.min_value is not None else None
            maximum = float(column.max_value) if column.max_value is not None else None
            if minimum is not None and minimum < 0 and _looks_non_negative(name):
                add(
                    name,
                    "IMPOSSIBLE VALUES",
                    Severity.CRITICAL,
                    f"минимум {minimum:g} при семантике, не допускающей отрицательных",
                )
            if (
                maximum is not None
                and column.mean is not None
                and column.mean > 0
                and maximum > column.mean * 1000
            ):
                add(
                    name,
                    "EXTREME OUTLIERS",
                    Severity.WARNING,
                    f"максимум {maximum:g} превышает среднее {column.mean:g} "
                    "более чем в тысячу раз",
                )

        if column.unique_count == 1 and profile.row_count > 1:
            add(
                name,
                "CONSTANT COLUMN",
                Severity.INFO,
                "во всех строках одно и то же значение",
            )

    # --- Дорогие проверки ---------------------------------------------------
    duplicate_rows: int | None = None
    duplicate_status = "OK"

    if expensive_allowed:
        frame = scan_table(paths)
        distinct = frame.unique().select(pl.len()).collect(engine="streaming").item()
        duplicate_rows = int(profile.row_count - distinct)
        if duplicate_rows > 0:
            add(
                None,
                "DUPLICATES",
                Severity.WARNING,
                "полностью совпадающие строки",
                duplicate_rows,
            )
    else:
        duplicate_status = SKIPPED
        skipped.append(
            f"DUPLICATES: {SKIPPED} (объём {profile.size_bytes / 1e9:.1f} ГБ "
            "превышает бюджет памяти для поиска полных дубликатов)"
        )

    for key in key_columns:
        key_column: ColumnProfile | None = next(
            (c for c in profile.columns if c.column_name == key), None
        )
        if key_column is None or key_column.unique_count is None:
            continue
        non_null = profile.row_count - key_column.null_count
        if key_column.unique_is_approximate:
            skipped.append(
                f"DUPLICATE KEYS / {key}: {SKIPPED} "
                "(сравнение опирается на приблизительный подсчёт уникальных)"
            )
            continue
        if key_column.unique_count < non_null:
            add(
                key,
                "DUPLICATE KEYS",
                Severity.CRITICAL,
                f"значение ключа повторяется: уникальных {key_column.unique_count} "
                f"при {non_null} непустых строках",
                non_null - key_column.unique_count,
            )

    # Расхождения написания категорий. Проверяются только столбцы с низкой
    # мощностью: на высокой мощности такая проверка неинформативна и дорога.
    categorical = [
        c.column_name
        for c in profile.columns
        if c.inferred_type == "string"
        and c.unique_count is not None
        and 1 < c.unique_count <= CATEGORY_MAX_CARDINALITY
    ]
    if categorical and expensive_allowed:
        frame = scan_table(paths)
        for name in categorical:
            collapsed = (
                frame.select(pl.col(name))
                .drop_nulls()
                .unique()
                .with_columns(_normalisation_key(pl.col(name)).alias("__key__"))
                .group_by("__key__")
                .agg(pl.len().alias("__variants__"))
                .filter(pl.col("__variants__") > 1)
                .select(pl.len())
                .collect(engine="streaming")
                .item()
            )
            if collapsed:
                add(
                    name,
                    "INCONSISTENT CATEGORY SPELLING",
                    Severity.WARNING,
                    f"групп значений, различающихся только регистром, пробелами "
                    f"или префиксом: {int(collapsed)}",
                )
    elif categorical:
        skipped.append(
            f"INCONSISTENT CATEGORY SPELLING: {SKIPPED} "
            "(объём выгрузки превышает бюджет проверки)"
        )

    return TableQuality(
        dataset=profile.dataset,
        table=profile.table,
        row_count=profile.row_count,
        duplicate_rows=duplicate_rows,
        duplicate_rows_status=duplicate_status,
        findings=findings,
        skipped_checks=skipped,
    )
