"""Правила проверки и их результат.

Проверки разделены на четыре уровня. Уровни различаются не строгостью,
а тем, что именно они знают: уровень файла не знает о столбцах, уровень
схемы не знает о значениях, уровень справочников не знает о бизнес-смысле,
и только уровень 4 сопоставляет значения между собой.

Отклонение строки — крайняя мера. Строка отклоняется, когда её включение
исказило бы смысл аналитики: нет даты, по которой строится ряд, или
дата не разобрана. Отсутствие необязательного поля основанием
не является: выгрузка, у которой половина профилей коек пуста, всё равно
отвечает на вопрос «сколько направлений пришло в организацию».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ValidationLevel(StrEnum):
    FILE = "FILE"
    SCHEMA = "SCHEMA"
    REFERENCE = "REFERENCE"
    BUSINESS = "BUSINESS"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class RowOutcome(StrEnum):
    VALID = "VALID"
    VALID_WITH_WARNING = "VALID_WITH_WARNING"
    REJECTED = "REJECTED"


class RuleCode(StrEnum):
    """Коды правил.

    Код входит в отчёт о качестве и в метрику. Он должен оставаться
    стабильным: по нему сравнивают поставки между собой.
    """

    # Уровень 1 — файл
    FILE_UNREADABLE = "FILE_UNREADABLE"
    FILE_EMPTY = "FILE_EMPTY"
    FILE_UNSUPPORTED_FORMAT = "FILE_UNSUPPORTED_FORMAT"

    # Уровень 2 — схема
    SCHEMA_MISSING_COLUMN = "SCHEMA_MISSING_COLUMN"
    SCHEMA_UNEXPECTED_COLUMN = "SCHEMA_UNEXPECTED_COLUMN"
    SCHEMA_UNPARSEABLE_VALUE = "SCHEMA_UNPARSEABLE_VALUE"

    # Уровень 3 — справочники
    UNMAPPED_ORGANIZATION = "UNMAPPED_ORGANIZATION"
    UNMAPPED_REGION = "UNMAPPED_REGION"
    UNMAPPED_PROFILE = "UNMAPPED_PROFILE"

    # Уровень 4 — бизнес-правила
    MISSING_REQUIRED_VALUE = "MISSING_REQUIRED_VALUE"
    INVALID_REGISTRATION_DATE = "INVALID_REGISTRATION_DATE"
    INVALID_REFUSAL_DATE = "INVALID_REFUSAL_DATE"
    INVALID_SNAPSHOT_DATE = "INVALID_SNAPSHOT_DATE"
    HOSPITALIZATION_BEFORE_REGISTRATION = "HOSPITALIZATION_BEFORE_REGISTRATION"
    REFUSAL_BEFORE_REGISTRATION = "REFUSAL_BEFORE_REGISTRATION"
    NEGATIVE_AGGREGATE = "NEGATIVE_AGGREGATE"
    DATE_OUT_OF_RANGE = "DATE_OUT_OF_RANGE"
    CONDITIONAL_NULL_EXPECTED = "CONDITIONAL_NULL_EXPECTED"
    DUPLICATE_SOURCE_KEY = "DUPLICATE_SOURCE_KEY"
    AUDIT_ROW_COUNT_DRIFT = "AUDIT_ROW_COUNT_DRIFT"


# Правила, при срабатывании которых строка отклоняется. Всё остальное
# даёт предупреждение и строку сохраняет.
REJECTING_RULES: frozenset[RuleCode] = frozenset(
    {
        RuleCode.MISSING_REQUIRED_VALUE,
        RuleCode.INVALID_REGISTRATION_DATE,
        RuleCode.INVALID_REFUSAL_DATE,
        RuleCode.INVALID_SNAPSHOT_DATE,
        RuleCode.NEGATIVE_AGGREGATE,
        RuleCode.DATE_OUT_OF_RANGE,
    }
)


@dataclass(slots=True)
class Finding:
    """Замечание в агрегированном виде.

    Замечание описывает столбец и число затронутых строк, но никогда —
    значения. Отчёт о качестве читают люди без доступа к медицинским
    данным, и он не должен становиться каналом их утечки.
    """

    level: ValidationLevel
    rule_code: RuleCode
    severity: Severity
    column_name: str | None
    affected_rows: int
    message: str

    def merge(self, other: Finding) -> None:
        self.affected_rows += other.affected_rows


@dataclass(slots=True)
class FindingCollector:
    """Накопитель замечаний с объединением по правилу и столбцу."""

    _items: dict[tuple[RuleCode, str | None], Finding] = field(default_factory=dict)

    def add(
        self,
        level: ValidationLevel,
        rule_code: RuleCode,
        severity: Severity,
        column_name: str | None,
        affected_rows: int,
        message: str,
    ) -> None:
        if affected_rows <= 0:
            return
        key = (rule_code, column_name)
        existing = self._items.get(key)
        if existing is None:
            self._items[key] = Finding(
                level=level,
                rule_code=rule_code,
                severity=severity,
                column_name=column_name,
                affected_rows=affected_rows,
                message=message,
            )
            return
        existing.affected_rows += affected_rows

    def findings(self) -> list[Finding]:
        return sorted(
            self._items.values(),
            key=lambda f: (f.severity != Severity.ERROR, f.rule_code.value),
        )

    @property
    def error_count(self) -> int:
        return sum(1 for f in self._items.values() if f.severity is Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(
            f.affected_rows
            for f in self._items.values()
            if f.severity is Severity.WARNING
        )
