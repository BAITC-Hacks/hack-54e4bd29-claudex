"""Strict HTTP contracts for persisted referral forecasts."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import DataScopeType

_RESPONSE = ConfigDict(extra="forbid", protected_namespaces=())


class HistoricalReferralPointResponse(BaseModel):
    model_config = _RESPONSE
    date: date
    value: int


class ReferralForecastPointResponse(BaseModel):
    model_config = _RESPONSE
    date: date
    predicted_value: float
    baseline_value: float
    delta_from_baseline: float


class ReferralForecastResponse(BaseModel):
    model_config = _RESPONSE

    id: uuid.UUID
    target: Literal["DAILY_REFERRAL_COUNT"]
    scope_type: DataScopeType
    hospital_id: uuid.UUID | None = None
    region_id: uuid.UUID | None = None
    horizon_days: int
    input_period_start: datetime
    input_period_end: datetime
    validation_period_start: date | None = None
    validation_period_end: date | None = None
    forecast_start: date
    forecast_end: date
    generated_at: datetime
    model_version: str
    selected_model: str
    baseline_model: str
    metrics: dict[str, Any]
    baseline_metrics: dict[str, Any]
    dataset_watermark: dict[str, Any]
    freshness_status: Literal["CURRENT", "STALE"]
    limitations: list[str]
    historical: list[HistoricalReferralPointResponse]
    forecast: list[ReferralForecastPointResponse]
    disclaimer: str
