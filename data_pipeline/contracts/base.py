"""Контракт набора данных.

Контракт — это то, что pipeline ожидает от файла, выраженное данными,
а не кодом. Причина в PHASE 3A: структура выгрузок известна из аудита
и будет меняться при следующих поставках. Изменение, выраженное правкой
таблицы, видно на code review целиком; изменение, размазанное по коду
разбора, — нет.

Контракт описывает только то, что подтверждено аудитом. Столбца, которого
в аудите нет, здесь тоже нет: придумать поле легко, а расхождение с
источником обнаружится уже на загрузке.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum


class ColumnKind(StrEnum):
    """Как значение столбца разбирается из текста файла."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATETIME = "datetime"


class Nullability(StrEnum):
    """Чем является пустое значение в этом столбце.

    Различие принципиальное. Пустая дата отказа в направлении означает,
    что отказа не было, — это нормальное состояние записи, а не дефект.
    Пустая дата регистрации означает, что запись непригодна. Один и тот же
    процент пропусков в отчёте аудита за этими двумя случаями скрывает
    разный смысл, и pipeline обязан их различать.
    """

    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    CONDITIONAL = "CONDITIONAL"


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    name: str
    kind: ColumnKind
    nullability: Nullability
    description: str
    # Доля пустых значений, зафиксированная Data Audit. Хранится не для
    # проверки, а для отчёта: резкое расхождение с ней означает, что
    # изменился либо источник, либо смысл поля.
    audit_null_pct: float | None = None
    # Пустое значение объяснимо этим условием. Заполняется только для
    # CONDITIONAL и попадает в документацию.
    conditional_reason: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetContract:
    """Полное описание одного набора данных."""

    key: str
    title: str
    source_system: str
    # Каталог внутри источника. Сопоставление по имени каталога, а не по
    # содержимому: угадывание набора по столбцам приводит к загрузке
    # не того файла не в ту таблицу.
    source_directory: str
    file_glob: str
    columns: tuple[ColumnSpec, ...]
    # Таблица ClickHouse, в которую набор превращается.
    target_table: str
    staging_table: str
    # Столбцы, значения которых нельзя переносить в аналитическое
    # хранилище в исходном виде ни при каких условиях.
    forbidden_in_analytics: frozenset[str] = field(default_factory=frozenset)
    # Ожидаемое число строк по данным аудита. Служит для отчёта
    # о расхождении, а не для отказа: поставка может обновиться.
    audit_row_count: int | None = None
    notes: tuple[str, ...] = ()

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    @property
    def required_columns(self) -> tuple[str, ...]:
        return tuple(
            column.name
            for column in self.columns
            if column.nullability is Nullability.REQUIRED
        )

    def column(self, name: str) -> ColumnSpec | None:
        for spec in self.columns:
            if spec.name == name:
                return spec
        return None

    def columns_of(self, kind: ColumnKind) -> tuple[ColumnSpec, ...]:
        return tuple(column for column in self.columns if column.kind is kind)


def require_columns(contract: DatasetContract, present: Sequence[str]) -> list[str]:
    """Столбцы контракта, которых нет в файле."""
    available = set(present)
    return [name for name in contract.column_names if name not in available]
