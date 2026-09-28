"""Проверка связуемости выгрузок между собой.

Вывод строится на фактическом пересечении множеств значений, а не на
совпадении имён столбцов. Совпадающее имя ничего не доказывает: в одной
выгрузке организация названа полным юридическим наименованием, в другой —
четырёхсимвольным кодом, и связать их по имени столбца невозможно.

Нечёткое сопоставление здесь не выполняется. Склейка похожих наименований
организаций меняет смысл данных и должна быть отдельным осознанным
решением, а не побочным эффектом аудита.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

import polars as pl

from data_pipeline.audit.profiler import scan_table

# Предел числа различных значений ключа, которые аудит удерживает в памяти.
# Ключ с большей мощностью для связи датасетов всё равно непригоден.
MAX_KEY_VALUES = 200_000


class JoinRole(StrEnum):
    REGION = "region"
    HOSPITAL = "hospital"
    DATE = "date"
    PROFILE = "profile"
    STABLE_KEY = "stable key"


class JoinStrength(StrEnum):
    STRONG = "STRONG JOIN"
    POSSIBLE = "POSSIBLE JOIN"
    WEAK = "WEAK JOIN"
    NONE = "NO JOIN"


ROLE_PATTERNS: dict[JoinRole, re.Pattern[str]] = {
    JoinRole.REGION: re.compile(
        r"(^|_)region($|_)|region_in|attach_region|^region$|^state$", re.IGNORECASE
    ),
    JoinRole.HOSPITAL: re.compile(
        r"medicine_organization|hospital_mo|referring_mo|mo_destination"
        r"|^org_in$|attach_org|clinic_name|medicine_organization_code",
        re.IGNORECASE,
    ),
    JoinRole.PROFILE: re.compile(r"bed_profile|profile_code|^profile$", re.IGNORECASE),
    JoinRole.DATE: re.compile(r"_dt$|_date$|^date", re.IGNORECASE),
    JoinRole.STABLE_KEY: re.compile(
        r"hospitalization_code|^id$|person_id", re.IGNORECASE
    ),
}


def detect_roles(columns: Sequence[str]) -> dict[JoinRole, list[str]]:
    roles: dict[JoinRole, list[str]] = {}
    for role, pattern in ROLE_PATTERNS.items():
        matched = [c for c in columns if pattern.search(c)]
        if matched:
            roles[role] = matched
    return roles


def _normalise(expr: pl.Expr) -> pl.Expr:
    """Привести значение к виду, пригодному для сравнения множеств.

    Регистр и пунктуация в наименованиях организаций различаются между
    выгрузками, и без приведения пересечение окажется пустым по причине,
    не имеющей отношения к сути данных.
    """
    return (
        expr.str.strip_chars()
        .str.to_lowercase()
        .str.replace_all(r"[\s\.\"'«»№,()-]+", "")
    )


@dataclass(slots=True)
class KeyValues:
    dataset: str
    column: str
    role: str
    distinct_count: int
    truncated: bool
    values: frozenset[str] = field(default_factory=frozenset, repr=False)


@dataclass(slots=True)
class JoinAssessment:
    left_dataset: str
    right_dataset: str
    role: str
    left_column: str
    right_column: str
    left_distinct: int
    right_distinct: int
    overlap: int
    left_coverage_pct: float
    right_coverage_pct: float
    strength: str
    rationale: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def collect_key_values(
    dataset: str,
    paths: Sequence[Path],
    column: str,
    role: JoinRole,
    limit: int = MAX_KEY_VALUES,
) -> KeyValues:
    """Собрать различные значения ключа одним потоковым проходом."""
    frame = (
        scan_table(paths)
        .select(_normalise(pl.col(column)).alias("__key__"))
        .drop_nulls()
        .filter(pl.col("__key__").str.len_chars() > 0)
        .unique()
        .head(limit + 1)
        .collect(engine="streaming")
    )
    values = frame["__key__"].to_list()
    truncated = len(values) > limit
    return KeyValues(
        dataset=dataset,
        column=column,
        role=role.value,
        distinct_count=len(values),
        truncated=truncated,
        values=frozenset(values[:limit]),
    )


def _strength(
    overlap: int, left: int, right: int, role: JoinRole
) -> tuple[JoinStrength, str]:
    if overlap == 0:
        return (
            JoinStrength.NONE,
            "Множества значений не пересекаются: общий ключ отсутствует",
        )
    smaller = min(left, right)
    coverage = overlap / smaller if smaller else 0.0
    if role is JoinRole.DATE:
        # Совпадение календарных дат неизбежно и само по себе не связь.
        return (
            JoinStrength.WEAK,
            "Общий календарный период позволяет сопоставлять агрегаты, "
            "но не отдельные записи",
        )
    if coverage >= 0.9:
        return (
            JoinStrength.STRONG,
            f"Пересечение покрывает {coverage:.0%} меньшего множества",
        )
    if coverage >= 0.5:
        return (
            JoinStrength.POSSIBLE,
            f"Пересечение покрывает {coverage:.0%} меньшего множества: "
            "часть записей останется несвязанной",
        )
    return (
        JoinStrength.WEAK,
        f"Пересечение покрывает лишь {coverage:.0%} меньшего множества",
    )


def assess(left: KeyValues, right: KeyValues) -> JoinAssessment:
    role = JoinRole(left.role)
    overlap = len(left.values & right.values)
    strength, rationale = _strength(
        overlap, left.distinct_count, right.distinct_count, role
    )
    if left.truncated or right.truncated:
        rationale += "; множество значений усечено пределом аудита, оценка занижена"
    return JoinAssessment(
        left_dataset=left.dataset,
        right_dataset=right.dataset,
        role=left.role,
        left_column=left.column,
        right_column=right.column,
        left_distinct=left.distinct_count,
        right_distinct=right.distinct_count,
        overlap=overlap,
        left_coverage_pct=round(
            100.0 * overlap / left.distinct_count if left.distinct_count else 0.0, 2
        ),
        right_coverage_pct=round(
            100.0 * overlap / right.distinct_count if right.distinct_count else 0.0, 2
        ),
        strength=strength.value,
        rationale=rationale,
    )


def build_matrix(assessments: Sequence[JoinAssessment]) -> dict[str, dict[str, str]]:
    """Свести оценки к матрице «роль ключа × пара выгрузок»."""
    matrix: dict[str, dict[str, str]] = {}
    for item in assessments:
        pair = f"{item.left_dataset} ↔ {item.right_dataset}"
        matrix.setdefault(item.role, {})[pair] = item.strength
    return matrix
