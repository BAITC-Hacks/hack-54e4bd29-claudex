"""Framework-free contracts for deterministic scenario analysis."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.models.enums import (
    BaselineFreshnessStatus,
    DataScopeType,
    ForecastStatus,
    ScenarioBaselineType,
    ScenarioType,
)


@dataclass(frozen=True, slots=True)
class ScenarioCalculation:
    baseline_value: Decimal
    assumption_value: Decimal
    calculated_value: Decimal
    delta_absolute: Decimal
    delta_percent: Decimal


@dataclass(frozen=True, slots=True)
class ScenarioBaseline:
    baseline_type: ScenarioBaselineType
    value: Decimal
    period_start: date
    period_end: date
    data_watermark: dict[str, object]
    sources: tuple[str, ...]
    limitations: tuple[str, ...]
    freshness_status: BaselineFreshnessStatus
    forecast_id: uuid.UUID | None = None
    model_version: str | None = None
    forecast_status: ForecastStatus | None = None
    selected_model: str | None = None
    forecast_generated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ScenarioScope:
    scope_type: DataScopeType
    region_id: uuid.UUID | None = None
    hospital_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ScenarioCommand:
    scenario_type: ScenarioType
    scope: ScenarioScope
    baseline_type: ScenarioBaselineType
    assumption_value: Decimal
    period_start: date | None = None
    period_end: date | None = None
    forecast_id: uuid.UUID | None = None
    historical_analysis: bool = False
    source_signal_id: uuid.UUID | None = None
    source_incident_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ScenarioPreview:
    scenario_type: ScenarioType
    scope: ScenarioScope
    baseline: ScenarioBaseline
    calculation: ScenarioCalculation
    formula_version: str
    limitations_version: str
    historical: bool


FORMULA_VERSION = "referral_inflow_change.v1"
LIMITATIONS_VERSION = "scenario_limitations.ru.v1"
SCENARIO_LIMITATIONS = (
    "Расчётный сценарий. Не является прогнозом или рекомендацией. "
    "Решение принимает уполномоченный сотрудник.",
    "Расчёт изменяет только входящий поток направлений и не моделирует "
    "койки, госпитализации, выписки, длительность лечения, персонал, "
    "занятость или дефицит мощности.",
)


__all__ = [
    "FORMULA_VERSION",
    "LIMITATIONS_VERSION",
    "SCENARIO_LIMITATIONS",
    "BaselineFreshnessStatus",
    "ScenarioBaseline",
    "ScenarioBaselineType",
    "ScenarioCalculation",
    "ScenarioCommand",
    "ScenarioPreview",
    "ScenarioScope",
]
