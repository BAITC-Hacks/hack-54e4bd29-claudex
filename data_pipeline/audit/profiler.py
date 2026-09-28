"""Потоковое профилирование табличных выгрузок.

Ограничение, определяющее всю конструкцию модуля: выгрузка может быть
больше доступной оперативной памяти. Поэтому файл никогда не загружается
целиком. Все метрики считаются одним ленивым проходом polars в потоковом
режиме, а число уникальных значений берётся приблизительным там, где
точный подсчёт потребовал бы удержания всех значений в памяти.

Второе ограничение: значения из источника не покидают модуль. Наружу
уходят счётчики, а минимум и максимум — только для столбцов, признанных
безопасными в privacy.py.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import polars as pl

from data_pipeline.audit.privacy import is_value_safe_to_publish

# Выше этого размера точный подсчёт уникальных значений и поиск полных
# дубликатов строк не выполняются: они требуют памяти порядка объёма
# самих данных.
EXACT_METRICS_LIMIT_BYTES = 1_500_000_000
# Размер выборки для определения схемы и формата дат.
SCHEMA_SAMPLE_ROWS = 20_000

SKIPPED = "SKIPPED_DUE_TO_RESOURCE_LIMIT"

# Строки, которые поставщики выгрузок используют вместо пустого значения.
NULL_TOKENS = ["", "NULL", "null", "NaN", "nan", "None", "-", "н/д", "нет данных"]


@dataclass(slots=True)
class ColumnProfile:
    column_name: str
    inferred_type: str
    nullable: bool
    null_count: int
    null_percentage: float
    unique_count: int | None
    unique_is_approximate: bool
    empty_string_count: int | None = None
    whitespace_padded_count: int | None = None
    min_value: str | None = None
    max_value: str | None = None
    mean: float | None = None
    median: float | None = None
    p05: float | None = None
    p95: float | None = None
    min_date: str | None = None
    max_date: str | None = None
    datetime_format: str | None = None
    value_sample_withheld: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TableProfile:
    dataset: str
    table: str
    files: list[str]
    size_bytes: int
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    exact_metrics: bool
    elapsed_seconds: float
    skipped_metrics: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["columns"] = [asdict(c) for c in self.columns]
        return payload


def scan_table(paths: Sequence[Path]) -> pl.LazyFrame:
    """Ленивое чтение выгрузки как одной таблицы.

    Части одной выгрузки читаются вместе: иначе строки будут посчитаны
    по файлам, а не по набору данных. Все столбцы читаются строками —
    тип выводится потом, по содержимому, а не по догадке parser'а. Это
    убирает целый класс ошибок, когда код организации вида «007K» в одной
    части выглядит числом, а в другой строкой.
    """
    return pl.scan_csv(
        [str(p) for p in paths],
        has_header=True,
        infer_schema=False,
        null_values=NULL_TOKENS,
        encoding="utf8",
        truncate_ragged_lines=False,
        low_memory=True,
    )


def _sample(paths: Sequence[Path], rows: int = SCHEMA_SAMPLE_ROWS) -> pl.DataFrame:
    return scan_table(paths[:1]).head(rows).collect()


# Форматы дат перечислены явно. Автоопределение polars отказывает на
# столбцах, где доля секунды присутствует не в каждой строке, а именно так
# выглядят выгрузки из источника. Спецификатор %.f допускает и отсутствие
# дробной части, и произвольное число знаков в ней.
DATETIME_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S%.f",
    "%Y-%m-%dT%H:%M:%S%.f",
    "%d.%m.%Y %H:%M:%S%.f",
    "%d/%m/%Y %H:%M:%S%.f",
)
DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")


def _detect_datetime_format(values: pl.Series) -> tuple[str, str] | None:
    """Подобрать формат, разбирающий все значения образца.

    Возвращает пару «вид столбца, строка формата» или None.
    """
    for fmt in DATETIME_FORMATS:
        parsed = values.str.to_datetime(format=fmt, strict=False, time_unit="us")
        if parsed.null_count() == 0:
            return "datetime", fmt
    for fmt in DATE_FORMATS:
        parsed = values.str.to_date(format=fmt, strict=False)
        if parsed.null_count() == 0:
            return "date", fmt
    return None


def _infer_type(series: pl.Series) -> tuple[str, str | None]:
    """Определить тип столбца по образцу непустых значений."""
    values = series.drop_nulls()
    if values.is_empty():
        return "empty", None

    stripped = values.str.strip_chars()
    non_empty = stripped.filter(stripped.str.len_chars() > 0)
    if non_empty.is_empty():
        return "empty", None

    detected = _detect_datetime_format(non_empty)
    if detected is not None:
        return detected

    parsed_int = non_empty.cast(pl.Int64, strict=False)
    if parsed_int.null_count() == 0:
        return "integer", None
    parsed_float = non_empty.cast(pl.Float64, strict=False)
    if parsed_float.null_count() == 0:
        return "float", None

    return "string", None


def profile_table(
    dataset: str,
    table: str,
    paths: Sequence[Path],
    size_bytes: int,
    progress: Callable[[str], None] | None = None,
) -> TableProfile:
    """Собрать профиль одной таблицы одним потоковым проходом."""
    started = time.monotonic()
    exact = size_bytes <= EXACT_METRICS_LIMIT_BYTES
    skipped: list[str] = []
    notes: list[str] = []

    if progress is not None:
        progress(f"{dataset} / {table}: определение схемы")

    sample = _sample(paths)
    columns = list(sample.columns)
    inferred = {name: _infer_type(sample[name]) for name in columns}
    types = {name: kind for name, (kind, _) in inferred.items()}
    formats = {name: fmt for name, (_, fmt) in inferred.items()}

    if not exact:
        skipped.append(
            f"exact_unique_count: {SKIPPED} "
            f"(объём {size_bytes / 1e9:.1f} ГБ, использован approx_n_unique)"
        )
        skipped.append(
            f"duplicate_row_count: {SKIPPED} "
            "(поиск полных дубликатов требует памяти порядка объёма данных)"
        )
        skipped.append(f"quantiles: {SKIPPED} (квантили не потоковые)")

    frame = scan_table(paths)
    aggregations: list[pl.Expr] = [pl.len().alias("__rows__")]

    for name in columns:
        col = pl.col(name)
        aggregations.append(col.null_count().alias(f"{name}::nulls"))
        if exact:
            aggregations.append(col.n_unique().alias(f"{name}::unique"))
        else:
            aggregations.append(col.approx_n_unique().alias(f"{name}::unique"))

        aggregations.append((col.str.len_chars() == 0).sum().alias(f"{name}::empty"))
        aggregations.append((col.str.strip_chars() != col).sum().alias(f"{name}::padded"))

        kind = types[name]
        if kind in {"integer", "float"}:
            numeric = col.cast(pl.Float64, strict=False)
            aggregations.append(numeric.min().alias(f"{name}::min"))
            aggregations.append(numeric.max().alias(f"{name}::max"))
            aggregations.append(numeric.mean().alias(f"{name}::mean"))
            aggregations.append(
                numeric.is_null().sum().alias(f"{name}::uncastable_nulls")
            )
            if exact:
                aggregations.append(numeric.median().alias(f"{name}::median"))
                aggregations.append(numeric.quantile(0.05).alias(f"{name}::p05"))
                aggregations.append(numeric.quantile(0.95).alias(f"{name}::p95"))
        elif kind in {"datetime", "date"}:
            parsed = (
                col.str.to_datetime(format=formats[name], strict=False, time_unit="us")
                if kind == "datetime"
                else col.str.to_date(format=formats[name], strict=False)
            )
            aggregations.append(parsed.min().alias(f"{name}::min_date"))
            aggregations.append(parsed.max().alias(f"{name}::max_date"))
            aggregations.append(
                (parsed.is_null() & col.is_not_null()).sum().alias(f"{name}::unparsed")
            )
        else:
            aggregations.append(col.min().alias(f"{name}::min"))
            aggregations.append(col.max().alias(f"{name}::max"))

    if progress is not None:
        progress(
            f"{dataset} / {table}: потоковый проход по "
            f"{len(paths)} файл(ам), {size_bytes / 1e6:.0f} МБ"
        )

    stats = frame.select(aggregations).collect(engine="streaming")
    row = stats.row(0, named=True)
    row_count = int(row["__rows__"])

    profiles: list[ColumnProfile] = []
    for name in columns:
        kind = types[name]
        nulls = int(row[f"{name}::nulls"])
        unique_raw = row[f"{name}::unique"]
        safe = is_value_safe_to_publish(name)
        column_notes: list[str] = []

        min_value = max_value = None
        min_date = max_date = None
        mean = median = p05 = p95 = None

        if kind in {"integer", "float"}:
            # Числовые границы не раскрывают личность и нужны для проверки
            # правдоподобия, поэтому публикуются независимо от имени столбца.
            min_value = _fmt(row.get(f"{name}::min"))
            max_value = _fmt(row.get(f"{name}::max"))
            mean = _float(row.get(f"{name}::mean"))
            median = _float(row.get(f"{name}::median"))
            p05 = _float(row.get(f"{name}::p05"))
            p95 = _float(row.get(f"{name}::p95"))
            bad = row.get(f"{name}::uncastable_nulls")
            if bad is not None and int(bad) > nulls:
                column_notes.append(
                    f"значений, не приводимых к числу: {int(bad) - nulls}"
                )
        elif kind in {"datetime", "date"}:
            min_date = _fmt(row.get(f"{name}::min_date"))
            max_date = _fmt(row.get(f"{name}::max_date"))
            unparsed = row.get(f"{name}::unparsed")
            if unparsed is not None and int(unparsed) > 0:
                column_notes.append(f"неразобранных дат: {int(unparsed)}")
        elif safe:
            min_value = _fmt(row.get(f"{name}::min"))
            max_value = _fmt(row.get(f"{name}::max"))

        profiles.append(
            ColumnProfile(
                column_name=name,
                inferred_type=kind,
                nullable=nulls > 0,
                null_count=nulls,
                null_percentage=round(100.0 * nulls / row_count, 4) if row_count else 0.0,
                unique_count=int(unique_raw) if unique_raw is not None else None,
                unique_is_approximate=not exact,
                empty_string_count=_int(row.get(f"{name}::empty")),
                whitespace_padded_count=_int(row.get(f"{name}::padded")),
                min_value=min_value,
                max_value=max_value,
                mean=mean,
                median=median,
                p05=p05,
                p95=p95,
                min_date=min_date,
                max_date=max_date,
                datetime_format=formats[name],
                value_sample_withheld=not safe and kind == "string",
                notes=column_notes,
            )
        )

    if not exact:
        notes.append(
            "Число уникальных значений приблизительное (HyperLogLog): "
            "точный подсчёт на этом объёме не выполняется."
        )

    return TableProfile(
        dataset=dataset,
        table=table,
        files=[p.name for p in paths],
        size_bytes=size_bytes,
        row_count=row_count,
        column_count=len(columns),
        columns=profiles,
        exact_metrics=exact,
        elapsed_seconds=round(time.monotonic() - started, 2),
        skipped_metrics=skipped,
        notes=notes,
    )


def _fmt(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 6)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int | float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None
