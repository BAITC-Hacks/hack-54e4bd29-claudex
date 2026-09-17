"""Neutral aggregate evidence shared by Signal Engine ports and adapters."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DailyAggregate:
    observed_on: date
    value: int
    is_complete: bool = True


@dataclass(frozen=True, slots=True)
class FreshnessEvidence:
    dataset_type: str
    source: str
    latest_successful_at: datetime | None
    watermark: dict[str, Any]


@dataclass(frozen=True, slots=True)
class QualityMeasurement:
    dataset_type: str
    source: str
    rule_code: str
    affected_rows: int
    eligible_rows: int | None
    denominator_code: str | None
    watermark: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TimeSeriesEvidence:
    dataset_type: str
    source: str
    points: tuple[DailyAggregate, ...]
    watermark: dict[str, Any]
    source_is_current: bool


@dataclass(frozen=True, slots=True)
class ForecastEvidence:
    forecast_id: uuid.UUID
    source: str
    freshness_status: str
    status: str
    horizon_start: date
    horizon_end: date
    forecast_value: float
    baseline_value: float
    selected_model: str
    selected_model_type: str
    model_version: str
    generated_at: datetime
    watermark: dict[str, Any]
