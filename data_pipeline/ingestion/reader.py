"""Чтение выгрузки пакетами.

Файл никогда не загружается в память целиком. Polars читает его лениво
и отдаёт пакетами заданного размера; расход памяти определяется размером
пакета, а не размером файла.

Все столбцы читаются строками. Определять тип средствами парсера нельзя:
код организации «007K» в одной части файла выглядит строкой, а «0071»
в другой — числом, и типы разошлись бы между частями одной выгрузки.
Разбор значений выполняет слой нормализации, по контракту.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from data_pipeline.contracts import DatasetContract, require_columns

DEFAULT_BATCH_SIZE = 50_000

# Строки, которыми поставщик обозначает отсутствующее значение.
NULL_TOKENS = ["", "NULL", "null", "NaN", "nan", "None"]


class SchemaMismatchError(Exception):
    """Файл не соответствует контракту набора.

    Возникает до чтения данных. Приводить файл к контракту молчаливым
    переименованием столбцов запрещено: расхождение означает, что
    изменился источник, и об этом должен узнать человек.
    """

    def __init__(self, dataset_key: str, missing: list[str], unexpected: list[str]):
        self.dataset_key = dataset_key
        self.missing = missing
        self.unexpected = unexpected
        parts = []
        if missing:
            parts.append("отсутствуют столбцы: " + ", ".join(missing))
        if unexpected:
            parts.append("лишние столбцы: " + ", ".join(unexpected))
        super().__init__(f"{dataset_key}: " + "; ".join(parts))


@dataclass(frozen=True, slots=True)
class FileSchema:
    columns: tuple[str, ...]
    matches_contract: bool
    missing: tuple[str, ...]
    unexpected: tuple[str, ...]


def read_header(path: Path) -> tuple[str, ...]:
    """Имена столбцов без чтения данных."""
    frame = pl.read_csv(path, n_rows=0, has_header=True, infer_schema=False)
    return tuple(frame.columns)


def inspect_schema(path: Path, contract: DatasetContract) -> FileSchema:
    columns = read_header(path)
    missing = require_columns(contract, columns)
    unexpected = [name for name in columns if contract.column(name) is None]
    return FileSchema(
        columns=columns,
        matches_contract=not missing and not unexpected,
        missing=tuple(missing),
        unexpected=tuple(unexpected),
    )


def ensure_schema(path: Path, contract: DatasetContract) -> FileSchema:
    schema = inspect_schema(path, contract)
    if not schema.matches_contract:
        raise SchemaMismatchError(
            contract.key, list(schema.missing), list(schema.unexpected)
        )
    return schema


def read_batches(
    path: Path,
    contract: DatasetContract,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Iterator[pl.DataFrame]:
    """Выдать содержимое файла пакетами по batch_size строк."""
    batches = (
        pl.scan_csv(
            path,
            has_header=True,
            infer_schema=False,
            null_values=NULL_TOKENS,
            encoding="utf8",
        )
        .select(contract.column_names)
        .collect_batches(chunk_size=batch_size, engine="streaming")
    )
    for frame in batches:
        if frame.height == 0:
            continue
        yield frame


def count_rows(path: Path) -> int:
    """Число строк данных в файле без загрузки его в память."""
    return int(
        pl.scan_csv(path, has_header=True, infer_schema=False)
        .select(pl.len())
        .collect(engine="streaming")
        .item()
    )
