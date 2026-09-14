"""Анализ временного покрытия.

Для прогнозирования важен не сам факт наличия даты, а то, можно ли из
столбца построить регулярный ряд. Поэтому модуль считает наблюдения по
месяцам и ищет разрывы, а не ограничивается минимумом и максимумом.

Подсчёт делается отдельным потоковым проходом по одному столбцу: это
дешевле, чем удерживать помесячную гистограмму по всем столбцам сразу.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import polars as pl

from data_pipeline.audit.profiler import scan_table

# Служебная отметка времени выгрузки. Она одинакова во всех строках файла
# и не является событием, поэтому не может быть осью временного ряда.
LOAD_TIMESTAMP_COLUMNS = frozenset({"sdu_load_date"})

# Порядок предпочтения оси ряда: сначала момент наступления события,
# затем плановые и производные даты.
PRIMARY_DATE_PREFERENCE: tuple[str, ...] = (
    "registration_dt",
    "refuse_dt",
    "vaccination_date",
    "injection_date",
    "hospitalization_dt",
    "planned_dt",
    "diagnosis_date",
    "take_in_date",
)

# Даты за этими границами считаются заведомо ошибочными. Верхняя граница
# намеренно не «сегодня»: плановая дата госпитализации в будущем нормальна.
PLAUSIBLE_MIN = dt.date(2015, 1, 1)
PLAUSIBLE_MAX_YEARS_AHEAD = 3


@dataclass(slots=True)
class DateColumnCoverage:
    column_name: str
    role: str
    non_null_count: int
    min_date: str | None
    max_date: str | None
    history_days: int | None
    distinct_days: int | None
    distinct_months: int | None
    granularity: str
    missing_months: list[str] = field(default_factory=list)
    implausible_past_count: int = 0
    future_count: int = 0
    after_today_count: int = 0
    monthly_counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TableTemporal:
    dataset: str
    table: str
    primary_date_column: str | None
    time_series_possible: bool
    columns: list[DateColumnCoverage]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["columns"] = [asdict(c) for c in self.columns]
        return payload


def _month_range(first: dt.date, last: dt.date) -> list[str]:
    months: list[str] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def _granularity(distinct_days: int, distinct_months: int, rows: int) -> str:
    if distinct_days == 0:
        return "unknown"
    if distinct_months <= 1 and distinct_days <= 1:
        return "single snapshot"
    if rows > distinct_days * 5:
        # На один день приходится много записей — это журнал событий,
        # а не заранее агрегированный ряд.
        return "event-level"
    if distinct_days >= distinct_months * 20:
        return "daily"
    if distinct_days >= distinct_months * 3:
        return "weekly"
    return "monthly"


def _pick_primary(candidates: Sequence[str]) -> str | None:
    for preferred in PRIMARY_DATE_PREFERENCE:
        if preferred in candidates:
            return preferred
    remaining = [c for c in candidates if c not in LOAD_TIMESTAMP_COLUMNS]
    return remaining[0] if remaining else (candidates[0] if candidates else None)


def analyze_table(
    dataset: str,
    table: str,
    paths: Sequence[Path],
    date_columns: dict[str, str],
) -> TableTemporal:
    """Посчитать покрытие по каждому столбцу-дате таблицы."""
    if not date_columns:
        return TableTemporal(
            dataset=dataset,
            table=table,
            primary_date_column=None,
            time_series_possible=False,
            columns=[],
            notes=["Столбцов с датой не обнаружено: временной ряд построить нельзя"],
        )

    primary = _pick_primary(list(date_columns))
    today = dt.date.today()
    horizon = dt.date(today.year + PLAUSIBLE_MAX_YEARS_AHEAD, today.month, 1)

    coverage: list[DateColumnCoverage] = []
    frame = scan_table(paths)

    for name, fmt in date_columns.items():
        # Формат без часов относится к столбцу типа «дата»: его нужно
        # разбирать как дату и только затем приводить к метке времени.
        parsed = (
            pl.col(name).str.to_datetime(format=fmt, strict=False, time_unit="us")
            if "%H" in fmt
            else pl.col(name)
            .str.to_date(format=fmt, strict=False)
            .cast(pl.Datetime("us"))
        )
        grouped = (
            frame.select(parsed.alias("__ts__"))
            .drop_nulls()
            .with_columns(
                pl.col("__ts__").dt.date().alias("__day__"),
                pl.col("__ts__").dt.truncate("1mo").dt.date().alias("__month__"),
            )
            .group_by("__month__")
            .agg(
                pl.len().alias("__n__"),
                pl.col("__day__").n_unique().alias("__days__"),
            )
            .sort("__month__")
            .collect(engine="streaming")
        )

        if grouped.is_empty():
            coverage.append(
                DateColumnCoverage(
                    column_name=name,
                    role="load timestamp" if name in LOAD_TIMESTAMP_COLUMNS else "event",
                    non_null_count=0,
                    min_date=None,
                    max_date=None,
                    history_days=None,
                    distinct_days=0,
                    distinct_months=0,
                    granularity="unknown",
                    notes=["Ни одно значение не разобрано как дата"],
                )
            )
            continue

        months = [m.strftime("%Y-%m") for m in grouped["__month__"].to_list()]
        counts = grouped["__n__"].to_list()
        month_dates = grouped["__month__"].to_list()
        non_null = int(sum(counts))
        distinct_days = int(grouped["__days__"].sum())

        plausible = [
            (m, c, d)
            for m, c, d in zip(months, counts, month_dates, strict=True)
            if PLAUSIBLE_MIN <= d <= horizon
        ]
        implausible_past = sum(
            c
            for m, c, d in zip(months, counts, month_dates, strict=True)
            if d < PLAUSIBLE_MIN
        )
        future = sum(
            c for m, c, d in zip(months, counts, month_dates, strict=True) if d > horizon
        )
        # Отдельно от планового горизонта: сколько записей датировано позже
        # сегодняшнего дня. Для плановой даты это нормально, для даты
        # свершившегося события — невозможно, и различать эти два случая
        # должен читатель отчёта, а не порог внутри кода.
        current_month = dt.date(today.year, today.month, 1)
        after_today = sum(
            c
            for m, c, d in zip(months, counts, month_dates, strict=True)
            if d > current_month
        )

        if plausible:
            first, last = plausible[0][2], plausible[-1][2]
            expected = _month_range(first, last)
            present = {m for m, _, _ in plausible}
            missing = [m for m in expected if m not in present]
            history_days = (last - first).days
        else:
            first = last = None
            missing = []
            history_days = None

        notes: list[str] = []
        if implausible_past:
            notes.append(
                f"значений с датой раньше {PLAUSIBLE_MIN.isoformat()}: {implausible_past}"
            )
        if future:
            notes.append(f"значений с датой позже {horizon.isoformat()}: {future}")
        if after_today:
            notes.append(
                f"значений с датой позже сегодняшнего дня "
                f"({today.isoformat()}): {after_today}. Для плановой даты это "
                "допустимо, для даты состоявшегося события — нет"
            )

        coverage.append(
            DateColumnCoverage(
                column_name=name,
                role="load timestamp" if name in LOAD_TIMESTAMP_COLUMNS else "event",
                non_null_count=non_null,
                min_date=first.isoformat() if first else None,
                max_date=last.isoformat() if last else None,
                history_days=history_days,
                distinct_days=distinct_days,
                distinct_months=len(plausible),
                granularity=_granularity(distinct_days, len(plausible), non_null),
                missing_months=missing,
                implausible_past_count=int(implausible_past),
                future_count=int(future),
                after_today_count=int(after_today),
                monthly_counts={m: int(c) for m, c, _ in plausible},
                notes=notes,
            )
        )

    primary_coverage = next((c for c in coverage if c.column_name == primary), None)
    possible = bool(
        primary_coverage
        and (primary_coverage.distinct_months or 0) >= 3
        and primary_coverage.non_null_count > 0
    )

    table_notes: list[str] = []
    if primary_coverage and primary_coverage.missing_months:
        table_notes.append(
            f"В основном столбце даты пропущено месяцев: "
            f"{len(primary_coverage.missing_months)}"
        )
    if not possible:
        table_notes.append(
            "История по основному столбцу короче трёх месяцев или отсутствует"
        )

    return TableTemporal(
        dataset=dataset,
        table=table,
        primary_date_column=primary,
        time_series_possible=possible,
        columns=coverage,
        notes=table_notes,
    )
