"""Оценка кандидатов на целевую переменную.

Целевая переменная не выбирается заранее. Модуль проверяет, какие из
рассматриваемых величин вообще вычислимы из фактически найденных столбцов,
и объясняет каждый вывод ссылкой на конкретные столбцы конкретной выгрузки.

Требование к каждому кандидату сформулировано декларативно: какие роли
столбцов обязаны присутствовать и должны ли они находиться в одной таблице.
Если обязательная роль не найдена, кандидат объявляется недоступным — без
попытки достроить недостающее поле предположением.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum

# Минимальная история, ниже которой ряд не считается пригодным для обучения.
MIN_MONTHS_FOR_TRAINING = 12
MIN_MONTHS_FOR_ANY_SERIES = 3


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIALLY AVAILABLE"
    NOT_AVAILABLE = "NOT AVAILABLE"


class Feasibility(StrEnum):
    GOOD = "GOOD"
    POSSIBLE = "POSSIBLE"
    WEAK = "WEAK"
    NOT_FEASIBLE = "NOT FEASIBLE"


@dataclass(slots=True)
class Requirement:
    """Одна обязательная или желательная роль столбца."""

    role: str
    pattern: re.Pattern[str]
    description: str
    required: bool = True
    same_table: bool = True


@dataclass(slots=True)
class TargetCandidate:
    key: str
    name: str
    definition: str
    requirements: tuple[Requirement, ...]


def _p(expr: str) -> re.Pattern[str]:
    return re.compile(expr, re.IGNORECASE)


CANDIDATES: tuple[TargetCandidate, ...] = (
    TargetCandidate(
        key="queue_size",
        name="queue_size(t+n)",
        definition=(
            "Число пациентов, ожидающих плановую госпитализацию, "
            "на организацию и профиль на горизонте n"
        ),
        requirements=(
            Requirement(
                "queue_registration",
                _p(r"^registration_dt$"),
                "дата постановки в очередь",
            ),
            Requirement(
                "organization",
                _p(r"mo_destination|hospital_mo|medicine_organization"),
                "принимающая организация",
            ),
            Requirement("profile", _p(r"profile"), "профиль койки", required=False),
            Requirement(
                "queue_exit",
                _p(r"^hospitalization_dt$|^admission_dt$"),
                "дата выбытия из очереди",
                required=False,
                same_table=False,
            ),
        ),
    ),
    TargetCandidate(
        key="incoming_referrals",
        name="incoming_referrals(t+n)",
        definition=(
            "Число направлений на плановую госпитализацию, поступивших "
            "в организацию за период"
        ),
        requirements=(
            Requirement(
                "referral_registration",
                _p(r"^registration_dt$"),
                "дата регистрации направления",
            ),
            Requirement(
                "receiving_organization",
                _p(r"hospital_mo|mo_destination"),
                "принимающая организация",
            ),
        ),
    ),
    TargetCandidate(
        key="waiting_time_days",
        name="waiting_time_days",
        definition=(
            "Число дней между постановкой в очередь и фактической " "госпитализацией"
        ),
        requirements=(
            Requirement(
                "queue_start",
                _p(r"^registration_dt$"),
                "дата постановки в очередь",
            ),
            Requirement(
                "queue_end",
                _p(r"^hospitalization_dt$"),
                "фактическая дата госпитализации в той же строке",
            ),
        ),
    ),
    TargetCandidate(
        key="refusal_rate",
        name="refusal_rate",
        definition=(
            "Доля отказов в плановой госпитализации от числа обращений "
            "за период по организации"
        ),
        requirements=(
            Requirement("refusal_event", _p(r"^refuse_dt$|^refusal_dt$"), "дата отказа"),
            Requirement(
                "refusal_organization",
                _p(r"^org_in$|hospital_mo"),
                "организация обращения",
            ),
            Requirement(
                "denominator",
                _p(r"^registration_dt$"),
                "знаменатель: обращения или направления за тот же период",
                same_table=False,
            ),
        ),
    ),
    TargetCandidate(
        key="treated_cases",
        name="treated_cases(t+n)",
        definition="Число пролеченных случаев по организации за период",
        requirements=(
            Requirement(
                "treated_measure",
                _p(r"discharged_total|treated_budget"),
                "показатель пролеченных случаев",
            ),
            Requirement(
                "treated_period",
                _p(r"^(?!sdu_load_date$).*(_dt|_date)$"),
                "дата отчётного периода, отличная от отметки выгрузки",
            ),
            Requirement(
                "treated_organization",
                _p(r"medicine_organization"),
                "организация",
            ),
        ),
    ),
    TargetCandidate(
        key="overload_risk_proxy",
        name="overload / risk proxy",
        definition=(
            "Составной показатель риска перегрузки: очередь, отказы и "
            "загрузка коечного фонда, сведённые к одной величине"
        ),
        requirements=(
            Requirement(
                "queue_component",
                _p(r"^registration_dt$"),
                "компонента очереди",
            ),
            Requirement(
                "refusal_component",
                _p(r"^refuse_dt$"),
                "компонента отказов",
                same_table=False,
            ),
            Requirement(
                "capacity_component",
                _p(r"bed_days|bed_capacity|koyka|коек"),
                "коечный фонд или его загрузка",
                same_table=False,
            ),
            Requirement(
                "ground_truth",
                _p(r"overload|перегруз|occupancy|загрузка_коек"),
                "наблюдаемая метка перегрузки",
            ),
        ),
    ),
)


@dataclass(slots=True)
class TableEvidence:
    """То, что аудит выяснил об одной таблице и что нужно для оценки."""

    dataset: str
    table: str
    columns: tuple[str, ...]
    row_count: int
    months_covered: int
    granularity: str
    time_series_possible: bool
    organization_distinct: int | None = None
    region_distinct: int | None = None


@dataclass(slots=True)
class RequirementResult:
    role: str
    description: str
    required: bool
    satisfied: bool
    found_in: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CandidateAssessment:
    key: str
    name: str
    definition: str
    status: str
    reason: str
    feasibility: str
    feasibility_reason: str
    supporting_tables: list[str] = field(default_factory=list)
    requirements: list[RequirementResult] = field(default_factory=list)
    leakage_risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["requirements"] = [asdict(r) for r in self.requirements]
        return payload


def _match(requirement: Requirement, evidence: Sequence[TableEvidence]) -> list[str]:
    """Таблицы, в которых нашлась требуемая роль столбца."""
    found: list[str] = []
    for table in evidence:
        if any(requirement.pattern.search(column) for column in table.columns):
            found.append(f"{table.dataset}.{table.table}")
    return found


def _feasibility(
    supporting: Sequence[TableEvidence],
    status: Availability,
) -> tuple[Feasibility, str]:
    if status is Availability.NOT_AVAILABLE:
        return (
            Feasibility.NOT_FEASIBLE,
            "Целевая величина не вычислима из имеющихся столбцов",
        )
    if not supporting:
        return Feasibility.NOT_FEASIBLE, "Нет таблицы, пригодной для построения ряда"

    months = max(t.months_covered for t in supporting)
    series = any(t.time_series_possible for t in supporting)

    if not series or months < MIN_MONTHS_FOR_ANY_SERIES:
        return (
            Feasibility.NOT_FEASIBLE,
            f"История покрывает {months} мес.: ряд построить нельзя",
        )
    if months < MIN_MONTHS_FOR_TRAINING:
        return (
            Feasibility.WEAK,
            f"История покрывает {months} мес.: годовая сезонность "
            "не наблюдается ни разу",
        )
    if status is Availability.PARTIAL:
        return (
            Feasibility.POSSIBLE,
            f"История {months} мес., но часть входных данных отсутствует "
            "или требует связывания выгрузок",
        )
    return (
        Feasibility.GOOD,
        f"История {months} мес. при событийной детализации и разрезе " "по организациям",
    )


def assess_candidates(evidence: Sequence[TableEvidence]) -> list[CandidateAssessment]:
    results: list[CandidateAssessment] = []

    for candidate in CANDIDATES:
        requirement_results: list[RequirementResult] = []
        for requirement in candidate.requirements:
            found = _match(requirement, evidence)
            requirement_results.append(
                RequirementResult(
                    role=requirement.role,
                    description=requirement.description,
                    required=requirement.required,
                    satisfied=bool(found),
                    found_in=found,
                )
            )

        mandatory = [
            (req, res)
            for req, res in zip(candidate.requirements, requirement_results, strict=True)
            if req.required
        ]
        missing = [res for req, res in mandatory if not res.satisfied]

        # Требования, помеченные same_table, должны выполняться в одной
        # таблице: величина, собранная из двух несвязанных выгрузок, —
        # это уже результат join'а, а не наблюдаемое значение.
        same_table_roles = [
            req for req, res in mandatory if req.same_table and res.satisfied
        ]
        co_located: list[str] = []
        for table in evidence:
            if all(
                any(req.pattern.search(c) for c in table.columns)
                for req in same_table_roles
            ):
                co_located.append(f"{table.dataset}.{table.table}")

        # Обязательное требование, помеченное как допустимое в другой
        # таблице, всё равно означает зависимость от связывания выгрузок:
        # величина перестаёт быть наблюдаемой и становится результатом join'а.
        cross_table = [
            res
            for req, res in mandatory
            if not req.same_table
            and res.satisfied
            and not (set(res.found_in) & set(co_located))
        ]

        if missing:
            status = Availability.NOT_AVAILABLE
            reason = "Отсутствуют обязательные поля: " + "; ".join(
                f"{r.role} ({r.description})" for r in missing
            )
        elif cross_table:
            status = Availability.PARTIAL
            reason = (
                "Часть обязательных полей находится в других выгрузках: "
                + "; ".join(f"{r.role} ({r.description})" for r in cross_table)
                + ". Величина вычислима только после связывания выгрузок"
            )
        elif same_table_roles and not co_located:
            status = Availability.PARTIAL
            reason = (
                "Все обязательные поля найдены, но не в одной таблице: "
                "величина вычислима только после связывания выгрузок"
            )
        else:
            optional_missing = [
                res
                for req, res in zip(
                    candidate.requirements, requirement_results, strict=True
                )
                if not req.required and not res.satisfied
            ]
            if optional_missing:
                status = Availability.PARTIAL
                reason = (
                    "Обязательные поля найдены; отсутствуют уточняющие: "
                    + "; ".join(f"{r.role} ({r.description})" for r in optional_missing)
                )
            else:
                status = Availability.AVAILABLE
                reason = "Все требуемые поля найдены в одной таблице"

        # Когда одной таблицы, содержащей всё нужное, нет, опорной считается
        # та, где найден определяющий показатель — первое обязательное
        # требование. Объединять сюда все таблицы, где нашлась хоть одна
        # роль, нельзя: глубина истории тогда берётся у постороннего набора
        # данных и оценка прогнозируемости становится ложной.
        defining = next((res for _, res in mandatory), None)
        supporting_names = set(co_located) or set(defining.found_in if defining else [])
        supporting = [t for t in evidence if f"{t.dataset}.{t.table}" in supporting_names]
        feasibility, feasibility_reason = _feasibility(supporting, status)

        results.append(
            CandidateAssessment(
                key=candidate.key,
                name=candidate.name,
                definition=candidate.definition,
                status=status.value,
                reason=reason,
                feasibility=feasibility.value,
                feasibility_reason=feasibility_reason,
                supporting_tables=sorted(supporting_names),
                requirements=requirement_results,
            )
        )

    return results


def recommend(assessments: Sequence[CandidateAssessment]) -> tuple[str | None, str]:
    """Выбрать целевую переменную либо отложить решение.

    Рекомендация выдаётся только при однозначном превосходстве одного
    кандидата. В остальных случаях выбор откладывается: неверно выбранная
    цель дороже отложенного решения.
    """
    ranked = [
        a
        for a in assessments
        if a.status == Availability.AVAILABLE.value
        and a.feasibility in {Feasibility.GOOD.value, Feasibility.POSSIBLE.value}
    ]
    if not ranked:
        return None, (
            "RECOMMENDATION DEFERRED: ни один кандидат не доступен полностью "
            "при пригодной для обучения истории"
        )

    order = {Feasibility.GOOD.value: 0, Feasibility.POSSIBLE.value: 1}
    ranked.sort(key=lambda a: order[a.feasibility])
    best = ranked[0]
    contenders = [a for a in ranked if a.feasibility == best.feasibility]
    if len(contenders) > 1:
        return None, (
            "RECOMMENDATION DEFERRED: несколько кандидатов равноценны — "
            + ", ".join(a.name for a in contenders)
            + ". Выбор требует решения владельца данных"
        )
    return best.name, best.feasibility_reason
