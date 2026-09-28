"""Детерминированная нормализация значений.

Каждое преобразование здесь обратимо в рассуждении: по нормализованному
значению видно, что именно с ним сделали. Нечёткого сопоставления нет
и не будет — склейка двух похожих наименований организаций меняет смысл
данных, и решение об этом принимает владелец данных, а не расстояние
Левенштейна.

Нормализация выполняется выражениями polars над целым пакетом, а не
построчно на Python: разница на полутора миллионах строк измеряется
минутами.
"""

from __future__ import annotations

import polars as pl

from data_pipeline.contracts import ColumnKind, DatasetContract

# Форматы отметок времени, подтверждённые Data Audit. Доля секунды
# присутствует не в каждой строке, поэтому %.f обязателен: он допускает
# и её отсутствие, и произвольное число знаков.
DATETIME_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S%.f",
    "%Y-%m-%dT%H:%M:%S%.f",
)

# Пунктуация, не несущая смысла в наименовании организации.
_ORG_NOISE = r"[\s]+"


def normalize_text(expr: pl.Expr) -> pl.Expr:
    """Обрезать пробелы и превратить пустую строку в отсутствующее значение.

    Пустая строка и NULL означают одно и то же — «значения нет», — но
    в агрегатах ведут себя по-разному. Расхождение устраняется на входе.
    """
    trimmed = expr.str.strip_chars()
    return pl.when(trimmed.str.len_chars() == 0).then(None).otherwise(trimmed)


def normalize_organization(expr: pl.Expr) -> pl.Expr:
    """Ключ организации для сопоставления между выгрузками.

    Схлопываются только регистр и повторяющиеся пробелы. Кавычки,
    скобки и номера сохраняются: «Поликлиника №1» и «Поликлиника №11» —
    разные организации, и удаление номера их бы объединило.
    """
    return (
        normalize_text(expr)
        .str.replace_all(_ORG_NOISE, " ")
        .str.strip_chars()
        .str.to_lowercase()
    )


def normalize_icd10(expr: pl.Expr) -> pl.Expr:
    """Код МКБ-10 в верхнем регистре без пробелов.

    Формат кода не проверяется и не исправляется: справочник МКБ-10
    содержит и диапазоны вида «C01-02», и коды с точкой. Приведение
    к «правильному» виду здесь исказило бы данные.
    """
    return normalize_text(expr).str.replace_all(r"\s+", "").str.to_uppercase()


def normalize_category(expr: pl.Expr) -> pl.Expr:
    """Категориальное значение: пробелы и регистр, ничего больше."""
    return normalize_text(expr)


def parse_datetime(expr: pl.Expr) -> pl.Expr:
    """Разобрать отметку времени по известным форматам.

    Значение, не подошедшее ни под один формат, становится пустым и будет
    поймано проверкой уровня 4. Молча подставлять текущее время нельзя:
    придуманная дата попадёт во временной ряд и исказит его.
    """
    text = normalize_text(expr)
    parsed = text.str.to_datetime(
        format=DATETIME_FORMATS[0], strict=False, time_unit="us"
    )
    for fmt in DATETIME_FORMATS[1:]:
        parsed = pl.coalesce(
            parsed, text.str.to_datetime(format=fmt, strict=False, time_unit="us")
        )
    return parsed


def parse_integer(expr: pl.Expr) -> pl.Expr:
    return normalize_text(expr).cast(pl.Int64, strict=False)


def parse_decimal(expr: pl.Expr) -> pl.Expr:
    return normalize_text(expr).cast(pl.Float64, strict=False)


RAW_SUFFIX = "__raw"


def normalized_frame(frame: pl.DataFrame, contract: DatasetContract) -> pl.DataFrame:
    """Привести пакет к типам контракта.

    Рядом с разобранным значением сохраняется исходный текст под именем
    со суффиксом `__raw`. Он нужен ровно для одного вопроса: отличить
    «значения не было» от «значение было, но разобрать его не удалось».
    Без такого различения испорченная дата выглядела бы как пропуск,
    а испорченных дат в источнике заведомо больше нуля.

    Исходные столбцы удаляются перед превращением строки в канонический
    вид — так сырой текст не может случайно попасть в хранилище.
    """
    expressions: list[pl.Expr] = []
    for column in contract.columns:
        source = pl.col(column.name)
        if column.kind is ColumnKind.DATETIME:
            parsed = parse_datetime(source)
        elif column.kind is ColumnKind.INTEGER:
            parsed = parse_integer(source)
        elif column.kind is ColumnKind.DECIMAL:
            parsed = parse_decimal(source)
        else:
            parsed = normalize_text(source)
        expressions.append(parsed.alias(column.name))
        if column.kind is not ColumnKind.STRING:
            expressions.append(normalize_text(source).alias(f"{column.name}{RAW_SUFFIX}"))
    return frame.select(expressions)


def drop_raw_columns(frame: pl.DataFrame) -> pl.DataFrame:
    """Убрать исходный текст перед канонизацией."""
    return frame.drop([name for name in frame.columns if name.endswith(RAW_SUFFIX)])
