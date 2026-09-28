"""Классификация столбцов по чувствительности.

Классификация построена на именах столбцов и на форме значений, но никогда
не на самих значениях: ни одно значение из источника не покидает этот
модуль. Наружу уходят только имя столбца, предполагаемый тип и счётчики.

Классификация намеренно осторожна. Ложная тревога стоит одного уточняющего
вопроса владельцу данных; пропущенный персональный идентификатор стоит
утечки.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import StrEnum


class Sensitivity(StrEnum):
    PUBLIC_REFERENCE = "PUBLIC/REFERENCE"
    OPERATIONAL = "OPERATIONAL"
    SENSITIVE = "SENSITIVE"
    PERSONAL = "PERSONAL"
    HIGHLY_SENSITIVE = "HIGHLY_SENSITIVE"


class Handling(StrEnum):
    KEEP = "KEEP"
    AGGREGATE = "AGGREGATE"
    PSEUDONYMIZE = "PSEUDONYMIZE"
    DROP_BEFORE_ANALYTICS = "DROP BEFORE ANALYTICS"
    RESTRICT_ACCESS = "RESTRICT ACCESS"


class RiskLevel(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(slots=True)
class Rule:
    pattern: re.Pattern[str]
    detected_type: str
    sensitivity: Sensitivity
    risk: RiskLevel
    handling: Handling
    rationale: str


def _p(expr: str) -> re.Pattern[str]:
    return re.compile(expr, re.IGNORECASE)


# Порядок важен: первое совпадение выигрывает, поэтому прямые
# идентификаторы личности стоят выше всего.
RULES: tuple[Rule, ...] = (
    Rule(
        _p(r"(^|_)(iin|iin_bin|bin)(_|$)|иин"),
        "Национальный идентификатор личности",
        Sensitivity.HIGHLY_SENSITIVE,
        RiskLevel.CRITICAL,
        Handling.DROP_BEFORE_ANALYTICS,
        "ИИН однозначно указывает на человека и не нужен для прогноза нагрузки",
    ),
    Rule(
        _p(r"(fio|full_name|last_name|first_name|surname|patronymic)|фамил|фио|отчеств"),
        "Имя физического лица",
        Sensitivity.HIGHLY_SENSITIVE,
        RiskLevel.CRITICAL,
        Handling.DROP_BEFORE_ANALYTICS,
        "Прямой идентификатор личности",
    ),
    Rule(
        _p(r"(phone|mobile|tel)|телефон"),
        "Номер телефона",
        Sensitivity.HIGHLY_SENSITIVE,
        RiskLevel.CRITICAL,
        Handling.DROP_BEFORE_ANALYTICS,
        "Контактные данные физического лица",
    ),
    Rule(
        _p(r"(^|_)(email|e_mail)(_|$)"),
        "Адрес электронной почты",
        Sensitivity.HIGHLY_SENSITIVE,
        RiskLevel.CRITICAL,
        Handling.DROP_BEFORE_ANALYTICS,
        "Контактные данные физического лица",
    ),
    Rule(
        _p(r"address|street|адрес|улиц|дом_|кварти"),
        "Адрес проживания",
        Sensitivity.HIGHLY_SENSITIVE,
        RiskLevel.CRITICAL,
        Handling.DROP_BEFORE_ANALYTICS,
        "Определяет место жительства конкретного человека",
    ),
    Rule(
        _p(
            r"(person_id|patient_id|patient_seq|number_card|card_no|card_number)|номер_карт"
        ),
        "Идентификатор или номер карты пациента",
        Sensitivity.PERSONAL,
        RiskLevel.HIGH,
        Handling.PSEUDONYMIZE,
        "Косвенный идентификатор: связывает записи одного человека между собой",
    ),
    Rule(
        _p(r"death_date|death_place|смерт"),
        "Сведения о смерти",
        Sensitivity.HIGHLY_SENSITIVE,
        RiskLevel.HIGH,
        Handling.AGGREGATE,
        "Особая категория данных о здоровье, пригодная для переидентификации",
    ),
    Rule(
        _p(r"диагноз|diagnos|icd|мкб|sickname|tumor|stage|локализац"),
        "Медицинский диагноз или код МКБ-10",
        Sensitivity.SENSITIVE,
        RiskLevel.MEDIUM,
        Handling.AGGREGATE,
        "Данные о здоровье: на уровне записи допустимы только в агрегате",
    ),
    Rule(
        _p(r"(^|_)age(_|$)|возраст|birth|дата_рожд"),
        "Возраст или дата рождения",
        Sensitivity.PERSONAL,
        RiskLevel.MEDIUM,
        Handling.AGGREGATE,
        "Квазиидентификатор: в сочетании с организацией и датой сужает круг лиц",
    ),
    Rule(
        _p(r"benefit|insured|social|льгот|застрахован|инвалид|соц"),
        "Социальный или страховой статус",
        Sensitivity.PERSONAL,
        RiskLevel.MEDIUM,
        Handling.AGGREGATE,
        "Квазиидентификатор и потенциальный источник дискриминации",
    ),
    Rule(
        _p(r"operation_code|operation_name|операц"),
        "Сведения о медицинском вмешательстве",
        Sensitivity.SENSITIVE,
        RiskLevel.MEDIUM,
        Handling.AGGREGATE,
        "Данные о здоровье на уровне записи",
    ),
    Rule(
        _p(r"amount|sum|payment|cost|price|сумма|оплат"),
        "Денежная величина",
        Sensitivity.OPERATIONAL,
        RiskLevel.LOW,
        Handling.AGGREGATE,
        "Финансовый показатель случая: интересен только в агрегате",
    ),
    Rule(
        _p(r"hospitalization_code|case_code|код_госпитал"),
        "Составной код случая госпитализации",
        Sensitivity.PERSONAL,
        RiskLevel.HIGH,
        Handling.PSEUDONYMIZE,
        "Содержит порядковый номер пациента и связывает записи одного случая",
    ),
    Rule(
        _p(r"region|state|область|регион|территор|resident"),
        "Территориальный признак",
        Sensitivity.PUBLIC_REFERENCE,
        RiskLevel.NONE,
        Handling.KEEP,
        "Административный справочник, обязательный разрез анализа",
    ),
    Rule(
        # «mo» и «org» — короткие подстроки, поэтому требуют границы имени
        # столбца, иначе правило сработает на любом слове с этими буквами.
        _p(r"(^|_)(mo|org)(_|$)|organization|clinic|hospital|provider|организац|клиник"),
        "Медицинская организация",
        Sensitivity.PUBLIC_REFERENCE,
        RiskLevel.NONE,
        Handling.KEEP,
        "Юридическое лицо, а не человек; основной разрез анализа",
    ),
    Rule(
        _p(r"profile|bed|profil|койк|профил"),
        "Профиль койки или отделения",
        Sensitivity.OPERATIONAL,
        RiskLevel.NONE,
        Handling.KEEP,
        "Операционный справочник",
    ),
    Rule(
        _p(r"(_dt|_date|date_|datetime|дата)"),
        "Дата или момент времени",
        Sensitivity.OPERATIONAL,
        RiskLevel.LOW,
        Handling.KEEP,
        "Необходима для временного ряда; риск возникает только вместе с идентификатором",
    ),
    Rule(
        _p(r"finance|источник_финанс"),
        "Источник финансирования",
        Sensitivity.OPERATIONAL,
        RiskLevel.NONE,
        Handling.KEEP,
        "Операционный справочник",
    ),
)

_FALLBACK = Rule(
    _p(r".*"),
    "Не классифицирован",
    Sensitivity.OPERATIONAL,
    RiskLevel.LOW,
    Handling.KEEP,
    "Имя столбца не совпало ни с одним правилом; требуется подтверждение "
    "владельца данных",
)


@dataclass(slots=True)
class ColumnPrivacy:
    column_name: str
    detected_type: str
    sensitivity: str
    risk_level: str
    handling: str
    rationale: str
    non_null_count: int | None = None
    unique_count: int | None = None
    unique_is_approximate: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_column(name: str) -> Rule:
    for rule in RULES:
        if rule.pattern.search(name):
            return rule
    return _FALLBACK


def classify(
    column_name: str,
    non_null_count: int | None = None,
    unique_count: int | None = None,
    unique_is_approximate: bool = False,
) -> ColumnPrivacy:
    rule = classify_column(column_name)
    return ColumnPrivacy(
        column_name=column_name,
        detected_type=rule.detected_type,
        sensitivity=rule.sensitivity.value,
        risk_level=rule.risk.value,
        handling=rule.handling.value,
        rationale=rule.rationale,
        non_null_count=non_null_count,
        unique_count=unique_count,
        unique_is_approximate=unique_is_approximate,
    )


def is_value_safe_to_publish(column_name: str) -> bool:
    """Можно ли показывать значения столбца в отчёте.

    Разрешено только для административных справочников. Всё остальное
    попадает в отчёт исключительно в виде счётчиков.
    """
    rule = classify_column(column_name)
    return rule.sensitivity is Sensitivity.PUBLIC_REFERENCE
