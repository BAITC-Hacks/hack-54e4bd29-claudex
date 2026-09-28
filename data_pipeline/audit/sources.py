"""Отнесение выгрузок к информационным системам-источникам.

Принадлежность определяется по совокупности признаков: названию каталога,
описанию поставщика и составу столбцов. Каждый вывод сопровождается
перечнем сработавших признаков и уровнем уверенности.

Насильно классификация не применяется. Выгрузка, для которой признаков
недостаточно, помечается UNKNOWN: ложная привязка к системе-источнику
повлечёт неверные ожидания о частоте обновления и о владельце данных.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(slots=True)
class SourceRule:
    source: str
    description: str
    name_patterns: tuple[re.Pattern[str], ...]
    column_patterns: tuple[re.Pattern[str], ...]


def _p(expr: str) -> re.Pattern[str]:
    return re.compile(expr, re.IGNORECASE)


RULES: tuple[SourceRule, ...] = (
    SourceRule(
        source="ИС БГ",
        description=(
            "Информационная система «Бюро госпитализации»: направления, "
            "очередь на плановую госпитализацию, отказы"
        ),
        name_patterns=(
            _p(r"направлен"),
            _p(r"ожидающ"),
            _p(r"отказ.*госпитализац"),
            _p(r"плановую госпитализац"),
        ),
        column_patterns=(
            _p(r"hospitalization_code"),
            _p(r"bed_profile|profile_code"),
            _p(r"referring_mo|mo_destination"),
            _p(r"refuse_dt|refusal_dt"),
        ),
    ),
    SourceRule(
        source="ЭРСБ",
        description=(
            "Электронный регистр стационарных больных: пролеченные случаи, "
            "койко-дни, исходы"
        ),
        name_patterns=(_p(r"пролеченн"), _p(r"стационарн"), _p(r"выбыл")),
        column_patterns=(
            _p(r"discharged_total|discharged_children"),
            _p(r"bed_days"),
            _p(r"treated_budget|treated_paid"),
            _p(r"deaths_total"),
        ),
    ),
    SourceRule(
        source="ЕИП / регистр вакцинации",
        description=(
            "Сведения об иммунизации: факты вакцинации, отказы и " "противопоказания"
        ),
        name_patterns=(_p(r"вакцинац"), _p(r"иммунизац"), _p(r"прививк")),
        column_patterns=(
            _p(r"vaccination_plan"),
            _p(r"vaccination_date|injection_date"),
            _p(r"contraindication"),
        ),
    ),
    SourceRule(
        source="Онкологический регистр",
        description=(
            "Сведения о злокачественных новообразованиях: впервые "
            "установленный диагноз, стадии, запущенность"
        ),
        name_patterns=(_p(r"онко"), _p(r"новообразован"), _p(r"запущенност")),
        column_patterns=(_p(r"tumor|stage|sickname"), _p(r"локализац")),
    ),
)

UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class SourceClassification:
    dataset: str
    probable_source: str
    confidence: str
    evidence: list[str] = field(default_factory=list)
    description: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_dataset(
    dataset: str,
    columns: tuple[str, ...],
    provider_description: str | None = None,
) -> SourceClassification:
    haystack = f"{dataset}\n{provider_description or ''}"

    best: tuple[int, SourceRule, list[str]] | None = None
    for rule in RULES:
        evidence: list[str] = []
        name_hits = sum(1 for p in rule.name_patterns if p.search(haystack))
        if name_hits:
            evidence.append(
                f"название или описание выгрузки совпало с {name_hits} признак(ами) "
                f"источника"
            )
        column_hits = 0
        for pattern in rule.column_patterns:
            matched = [c for c in columns if pattern.search(c)]
            if matched:
                column_hits += 1
                evidence.append("столбцы: " + ", ".join(sorted(matched)))
        score = name_hits * 2 + column_hits
        if score and (best is None or score > best[0]):
            best = (score, rule, evidence)

    if best is None:
        return SourceClassification(
            dataset=dataset,
            probable_source=UNKNOWN,
            confidence=Confidence.LOW.value,
            evidence=["Ни имя выгрузки, ни состав столбцов не дали совпадений"],
        )

    score, rule, evidence = best
    if score >= 4:
        confidence = Confidence.HIGH
    elif score >= 2:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    return SourceClassification(
        dataset=dataset,
        probable_source=rule.source,
        confidence=confidence.value,
        evidence=evidence,
        description=rule.description,
    )
