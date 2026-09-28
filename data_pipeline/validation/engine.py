"""Применение правил к пакету строк.

Проверки выражены столбцовыми операциями polars: пакет размечается
булевыми масками, и по маскам считается число затронутых строк. Обход
строк на Python дал бы тот же ответ на порядок медленнее.

Границы правдоподобия дат заданы явно и намеренно широко. Задача проверки
здесь — поймать испорченное значение вроде года 0001, а не заменить
собой суждение владельца данных о том, какая дата допустима.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import polars as pl

from data_pipeline.contracts import ColumnKind, DatasetContract, Nullability
from data_pipeline.validation.rules import (
    REJECTING_RULES,
    FindingCollector,
    RuleCode,
    Severity,
    ValidationLevel,
)

# Нижняя граница правдоподобия. Событий системы бюро госпитализации
# раньше этой даты не существует.
PLAUSIBLE_MIN = dt.datetime(2015, 1, 1)
# Верхняя граница задаётся с запасом: плановая дата госпитализации
# законно уходит вперёд, и обрезать её по «сегодня» было бы ошибкой.
PLAUSIBLE_MAX_YEARS_AHEAD = 5

REJECT_COLUMN = "__rejected__"
WARN_COLUMN = "__warned__"
REASON_COLUMN = "__reject_reasons__"


@dataclass(frozen=True, slots=True)
class DateAxis:
    """Столбец, по которому строится временной ряд набора."""

    column: str
    invalid_rule: RuleCode


DATE_AXES: dict[str, DateAxis] = {
    "REFERRALS": DateAxis("registration_dt", RuleCode.INVALID_REGISTRATION_DATE),
    "WAITING": DateAxis("registration_dt", RuleCode.INVALID_REGISTRATION_DATE),
    "REFUSALS": DateAxis("refuse_dt", RuleCode.INVALID_REFUSAL_DATE),
    "TREATED": DateAxis("sdu_load_date", RuleCode.INVALID_SNAPSHOT_DATE),
}

# Пары «событие — начало отсчёта», сравнимые по смыслу. Пара включается
# только там, где обе даты относятся к одному случаю; сравнивать даты
# из разных выгрузок нельзя.
ORDERED_DATE_PAIRS: dict[str, tuple[tuple[str, str, RuleCode], ...]] = {
    "REFERRALS": (
        (
            "hospitalization_dt",
            "registration_dt",
            RuleCode.HOSPITALIZATION_BEFORE_REGISTRATION,
        ),
        ("refusal_dt", "registration_dt", RuleCode.REFUSAL_BEFORE_REGISTRATION),
    ),
}


def _plausible_max() -> dt.datetime:
    today = dt.date.today()
    return dt.datetime(today.year + PLAUSIBLE_MAX_YEARS_AHEAD, 1, 1)


@dataclass(slots=True)
class BatchValidation:
    """Размеченный пакет и накопленные замечания."""

    frame: pl.DataFrame
    rows_read: int

    @property
    def valid(self) -> pl.DataFrame:
        return self.frame.filter(~pl.col(REJECT_COLUMN))

    @property
    def rejected(self) -> pl.DataFrame:
        return self.frame.filter(pl.col(REJECT_COLUMN))


def validate_batch(
    frame: pl.DataFrame,
    contract: DatasetContract,
    collector: FindingCollector,
) -> BatchValidation:
    """Разметить пакет и записать замечания.

    Возвращается тот же пакет с тремя служебными столбцами: признак
    отклонения, признак предупреждения и перечень кодов причин.
    Столбцы удаляются перед преобразованием в канонический вид.
    """
    rows = frame.height
    # Булевы литералы polars: начальное значение маски, а не флаг функции.
    reject = pl.lit(False)
    warn = pl.lit(False)
    reasons: list[pl.Expr] = []

    def mark(condition: pl.Expr, code: RuleCode) -> None:
        """Добавить условие в маску отклонения или предупреждения.

        Пустое значение приводится к «условие не выполнено». Без этого
        сравнение с отсутствующим числом даёт NULL, вся маска становится
        NULL, и строка не попадает ни в принятые, ни в отклонённые —
        она просто исчезает. Именно так теряется четверть отказов,
        у которых не указана сумма.
        """
        nonlocal reject, warn
        safe = condition.fill_null(value=False)
        if code in REJECTING_RULES:
            reject = reject | safe
            reasons.append(pl.when(safe).then(pl.lit(code.value)).otherwise(pl.lit(None)))
        else:
            warn = warn | safe

    # --- Уровень 2: значения, не поддавшиеся разбору ------------------------
    for column in contract.columns:
        if column.kind is ColumnKind.STRING:
            continue
        original = pl.col(f"{column.name}__raw")
        parsed = pl.col(column.name)
        unparseable = original.is_not_null() & parsed.is_null()
        count = int(frame.select(unparseable.sum()).item()) if rows else 0
        collector.add(
            ValidationLevel.SCHEMA,
            RuleCode.SCHEMA_UNPARSEABLE_VALUE,
            Severity.WARNING,
            column.name,
            count,
            f"{count} строк содержат значение, не разобранное как {column.kind.value}",
        )

    # --- Уровень 4: обязательные значения -----------------------------------
    for column in contract.columns:
        if column.nullability is not Nullability.REQUIRED:
            continue
        missing = pl.col(column.name).is_null()
        count = int(frame.select(missing.sum()).item()) if rows else 0
        collector.add(
            ValidationLevel.BUSINESS,
            RuleCode.MISSING_REQUIRED_VALUE,
            Severity.ERROR,
            column.name,
            count,
            f"{count} строк не содержат обязательное значение",
        )
        mark(missing, RuleCode.MISSING_REQUIRED_VALUE)

    # Пропуски в условно пустых столбцах фиксируются как сведения,
    # а не как дефект: их отсутствие объяснено контрактом.
    for column in contract.columns:
        if column.nullability is not Nullability.CONDITIONAL:
            continue
        missing = pl.col(column.name).is_null()
        count = int(frame.select(missing.sum()).item()) if rows else 0
        collector.add(
            ValidationLevel.BUSINESS,
            RuleCode.CONDITIONAL_NULL_EXPECTED,
            Severity.INFO,
            column.name,
            count,
            f"{count} строк без значения; ожидаемо: {column.conditional_reason}",
        )

    # --- Уровень 4: ось временного ряда -------------------------------------
    axis = DATE_AXES.get(contract.key)
    if axis is not None:
        # Имя отличается от `column` выше намеренно: там идёт описание
        # столбца контракта, здесь — выражение polars.
        axis_expr = pl.col(axis.column)
        broken = axis_expr.is_null()
        out_of_range = axis_expr.is_not_null() & (
            (axis_expr < pl.lit(PLAUSIBLE_MIN)) | (axis_expr > pl.lit(_plausible_max()))
        )
        broken_count = int(frame.select(broken.sum()).item()) if rows else 0
        range_count = int(frame.select(out_of_range.sum()).item()) if rows else 0
        collector.add(
            ValidationLevel.BUSINESS,
            axis.invalid_rule,
            Severity.ERROR,
            axis.column,
            broken_count,
            f"{broken_count} строк не содержат разобранную дату оси ряда",
        )
        collector.add(
            ValidationLevel.BUSINESS,
            RuleCode.DATE_OUT_OF_RANGE,
            Severity.ERROR,
            axis.column,
            range_count,
            f"{range_count} строк содержат дату вне правдоподобных границ",
        )
        mark(broken, axis.invalid_rule)
        mark(out_of_range, RuleCode.DATE_OUT_OF_RANGE)

    # --- Уровень 4: порядок дат внутри случая -------------------------------
    for later, earlier, code in ORDERED_DATE_PAIRS.get(contract.key, ()):
        both = pl.col(later).is_not_null() & pl.col(earlier).is_not_null()
        wrong = both & (pl.col(later) < pl.col(earlier))
        count = int(frame.select(wrong.sum()).item()) if rows else 0
        collector.add(
            ValidationLevel.BUSINESS,
            code,
            Severity.WARNING,
            later,
            count,
            f"{count} строк содержат {later} раньше {earlier}",
        )
        mark(wrong, code)

    # --- Уровень 4: неотрицательные агрегаты --------------------------------
    for column in contract.columns:
        if column.kind not in (ColumnKind.INTEGER, ColumnKind.DECIMAL):
            continue
        negative = pl.col(column.name) < 0
        count = int(frame.select(negative.sum()).item()) if rows else 0
        collector.add(
            ValidationLevel.BUSINESS,
            RuleCode.NEGATIVE_AGGREGATE,
            Severity.ERROR,
            column.name,
            count,
            f"{count} строк содержат отрицательное значение в счётном поле",
        )
        mark(negative, RuleCode.NEGATIVE_AGGREGATE)

    reason_expr = (
        pl.concat_list(reasons).list.drop_nulls().list.join(",")
        if reasons
        else pl.lit("")
    )
    marked = frame.with_columns(
        reject.alias(REJECT_COLUMN),
        warn.alias(WARN_COLUMN),
        reason_expr.alias(REASON_COLUMN),
    )
    return BatchValidation(frame=marked, rows_read=rows)
