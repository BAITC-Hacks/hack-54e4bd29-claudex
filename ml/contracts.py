"""Framework-independent contracts for short-horizon referral forecasting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

FEATURE_SCHEMA_VERSION = "referrals_daily_v1"


@dataclass(frozen=True, slots=True)
class DailyObservation:
    observed_on: date
    value: float


@dataclass(frozen=True, slots=True)
class DatasetMetadata:
    period_start: date
    period_end: date
    row_count: int
    regions_included: tuple[str, ...]
    source_watermark: str
    feature_schema_version: str
    missing_dates: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class ForecastDataset:
    observations: tuple[DailyObservation, ...]
    metadata: DatasetMetadata


@dataclass(frozen=True, slots=True)
class FeatureRow:
    target_date: date
    target: float
    lag_1: float
    lag_2: float
    lag_3: float
    lag_7: float
    rolling_mean_7: float
    rolling_std_7: float
    day_of_week: int

    @property
    def features(self) -> tuple[float, ...]:
        return (
            self.lag_1,
            self.lag_2,
            self.lag_3,
            self.lag_7,
            self.rolling_mean_7,
            self.rolling_std_7,
            float(self.day_of_week),
        )


@dataclass(frozen=True, slots=True)
class ValidationFold:
    index: int
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date


@dataclass(frozen=True, slots=True)
class MetricSet:
    mae: float
    wape: float | None
    rmse: float


@dataclass(frozen=True, slots=True)
class FoldEvaluation:
    fold: ValidationFold
    metrics: MetricSet


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    model_name: str
    model_type: str
    overall: MetricSet
    folds: tuple[FoldEvaluation, ...]


@dataclass(frozen=True, slots=True)
class SelectionResult:
    selected: CandidateEvaluation
    strongest_baseline: CandidateEvaluation
    ml_selected: bool
    rationale: str


@dataclass(frozen=True, slots=True)
class ForecastValue:
    forecast_date: date
    predicted_value: float
    baseline_value: float


@dataclass(frozen=True, slots=True)
class TrainingResult:
    generated_at: datetime
    dataset: ForecastDataset
    evaluations: tuple[CandidateEvaluation, ...]
    selection: SelectionResult
    forecast: tuple[ForecastValue, ...]
