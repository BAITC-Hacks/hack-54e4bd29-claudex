"""Strict API contracts for Phase 7 Scenario Analysis."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    BaselineFreshnessStatus,
    DataScopeType,
    ForecastStatus,
    ScenarioBaselineType,
    ScenarioStatus,
    ScenarioType,
)

_REQUEST = ConfigDict(extra="forbid")
_RESPONSE = ConfigDict(extra="forbid", protected_namespaces=())


class ScenarioRequest(BaseModel):
    model_config = _REQUEST

    scenario_type: ScenarioType
    scope_type: DataScopeType
    region_id: uuid.UUID | None = None
    hospital_id: uuid.UUID | None = None
    baseline_type: ScenarioBaselineType
    assumption_value: Decimal
    period_start: date | None = None
    period_end: date | None = None
    forecast_id: uuid.UUID | None = None
    historical_analysis: bool = False
    source_signal_id: uuid.UUID | None = None
    source_incident_id: uuid.UUID | None = None


class ScenarioCreateRequest(ScenarioRequest):
    client_request_id: uuid.UUID


class ScenarioResponse(BaseModel):
    model_config = _RESPONSE

    id: uuid.UUID | None = None
    scenario_type: ScenarioType
    scope_type: DataScopeType
    region_id: uuid.UUID | None = None
    hospital_id: uuid.UUID | None = None
    created_by: uuid.UUID | None = None
    source_signal_id: uuid.UUID | None = None
    source_incident_id: uuid.UUID | None = None
    baseline_type: ScenarioBaselineType
    baseline_value: Decimal
    baseline_period_start: date
    baseline_period_end: date
    assumption_value: Decimal
    calculated_value: Decimal
    delta_absolute: Decimal
    delta_percent: Decimal
    data_watermark: dict[str, Any]
    forecast_id: uuid.UUID | None = None
    model_version: str | None = None
    forecast_status: ForecastStatus | None = None
    baseline_freshness_status: BaselineFreshnessStatus
    selected_model: str | None = None
    forecast_generated_at: datetime | None = None
    formula_version: str
    limitations_version: str
    limitations: list[str]
    historical: bool
    status: ScenarioStatus | None = None
    created_at: datetime | None = None


class ScenarioListItem(ScenarioResponse):
    pass
