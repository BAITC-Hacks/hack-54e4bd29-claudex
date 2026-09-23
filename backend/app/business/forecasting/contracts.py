"""Stable business contracts at the forecasting/ML boundary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from app.shared.forecasting import (
    DailyReferralCount,
    OrganizationForecastInput,
    OrganizationForecastRequest,
    ReferralDatasetWatermark,
)


@dataclass(frozen=True, slots=True)
class ForecastMetricSet:
    mae: float
    wape: float | None
    rmse: float

    def as_dict(self) -> dict[str, float | None]:
        return {"mae": self.mae, "wape": self.wape, "rmse": self.rmse}


@dataclass(frozen=True, slots=True)
class ForecastPointResult:
    forecast_date: date
    predicted_value: float
    baseline_value: float

    @property
    def delta_from_baseline(self) -> float:
        return self.predicted_value - self.baseline_value


@dataclass(frozen=True, slots=True)
class ForecastEngineResult:
    generated_at: datetime
    input_period_start: date
    input_period_end: date
    training_rows: int
    feature_schema_version: str
    selected_model: str
    selected_model_type: str
    model_version: str
    mlflow_run_id: str
    metrics: ForecastMetricSet
    strongest_baseline: str
    baseline_metrics: ForecastMetricSet
    validation_folds: tuple[dict[str, object], ...]
    candidate_metrics: tuple[dict[str, object], ...]
    selection_rationale: str
    points: tuple[ForecastPointResult, ...]
    organization_evidence: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ReferralForecastSnapshot:
    id: uuid.UUID
    generated_at: datetime
    input_period_start: datetime
    input_period_end: datetime
    forecast_start: date
    forecast_end: date
    model_version: str
    selected_model: str
    baseline_model: str
    metrics: dict[str, object]
    baseline_metrics: dict[str, object]
    dataset_watermark: dict[str, object]
    freshness_status: str
    limitations: tuple[str, ...]
    historical: tuple[DailyReferralCount, ...]
    points: tuple[ForecastPointResult, ...]
    scope_type: str = "GLOBAL"
    hospital_id: uuid.UUID | None = None
    region_id: uuid.UUID | None = None


__all__ = [
    "DailyReferralCount",
    "ForecastEngineResult",
    "ForecastMetricSet",
    "ForecastPointResult",
    "OrganizationForecastInput",
    "OrganizationForecastRequest",
    "ReferralDatasetWatermark",
    "ReferralForecastSnapshot",
]
