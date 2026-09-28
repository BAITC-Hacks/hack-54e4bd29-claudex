"""Adapter from backend forecasting ports to the independent ML package."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Protocol, cast

from app.business.forecasting.contracts import (
    DailyReferralCount,
    ForecastEngineResult,
    ForecastMetricSet,
    ForecastPointResult,
    ReferralDatasetWatermark,
)
from app.business.forecasting.service import ForecastTrainingService
from app.composition import get_unit_of_work_factory
from app.core.config import get_settings
from app.database.clickhouse import get_client as get_clickhouse_client
from app.database.postgres import get_session_factory
from app.repositories.clickhouse_forecasting import (
    ClickHouseQueryClient,
    ClickHouseReferralHistoryRepository,
)
from app.repositories.forecast_metadata import SqlAlchemyForecastMetadataRepository
from ml.contracts import MetricSet, TrainingResult
from ml.dataset import build_daily_dataset
from ml.evaluation import run_training
from ml.tracking import MlflowExperimentTracker, TrackedModel


class ExperimentTracker(Protocol):
    def track(self, result: TrainingResult) -> TrackedModel: ...


def _metric(raw: MetricSet) -> ForecastMetricSet:
    return ForecastMetricSet(raw.mae, raw.wape, raw.rmse)


class ReferralForecastEngine:
    def __init__(
        self,
        *,
        tracker: ExperimentTracker,
        horizon_days: int = 7,
        min_train_days: int = 42,
        minimum_relative_improvement: float = 0.02,
    ) -> None:
        self._tracker = tracker
        self._horizon_days = horizon_days
        self._min_train_days = min_train_days
        self._minimum_relative_improvement = minimum_relative_improvement

    def train(
        self,
        history: tuple[DailyReferralCount, ...],
        watermark: ReferralDatasetWatermark,
        *,
        generated_at: datetime,
    ) -> ForecastEngineResult:
        watermark_json = json.dumps(
            watermark.as_dict(), sort_keys=True, separators=(",", ":")
        )
        dataset = build_daily_dataset(
            ((item.observed_on, item.count) for item in history),
            source_watermark=watermark_json,
        )
        result = run_training(
            dataset,
            generated_at=generated_at,
            horizon=self._horizon_days,
            min_train_size=self._min_train_days,
            minimum_relative_improvement=self._minimum_relative_improvement,
        )
        tracked = self._tracker.track(result)
        selected = result.selection.selected
        baseline = result.selection.strongest_baseline
        return ForecastEngineResult(
            generated_at=result.generated_at,
            input_period_start=dataset.metadata.period_start,
            input_period_end=dataset.metadata.period_end,
            training_rows=dataset.metadata.row_count,
            feature_schema_version=dataset.metadata.feature_schema_version,
            selected_model=selected.model_name,
            selected_model_type=selected.model_type,
            model_version=tracked.model_version,
            mlflow_run_id=tracked.run_id,
            metrics=_metric(selected.overall),
            strongest_baseline=baseline.model_name,
            baseline_metrics=_metric(baseline.overall),
            validation_folds=tuple(
                {
                    "index": item.fold.index,
                    "train_start": item.fold.train_start.isoformat(),
                    "train_end": item.fold.train_end.isoformat(),
                    "validation_start": item.fold.validation_start.isoformat(),
                    "validation_end": item.fold.validation_end.isoformat(),
                    "metrics": _metric(item.metrics).as_dict(),
                }
                for item in selected.folds
            ),
            candidate_metrics=tuple(
                {
                    "model": item.model_name,
                    "model_type": item.model_type,
                    **_metric(item.overall).as_dict(),
                }
                for item in result.evaluations
            ),
            selection_rationale=result.selection.rationale,
            points=tuple(
                ForecastPointResult(
                    item.forecast_date,
                    item.predicted_value,
                    item.baseline_value,
                )
                for item in result.forecast
            ),
        )


def build_forecast_training_service() -> ForecastTrainingService:
    """Composition used only by the ML worker/CLI image."""
    settings = get_settings()
    client = cast(ClickHouseQueryClient, get_clickhouse_client())
    tracker = MlflowExperimentTracker(
        tracking_uri=settings.mlflow_tracking_uri,
        experiment_name=settings.mlflow_experiment_name,
        registered_model_name=settings.mlflow_registered_model_name,
    )
    metadata = SqlAlchemyForecastMetadataRepository(get_session_factory())
    return ForecastTrainingService(
        history_repository=ClickHouseReferralHistoryRepository(
            client,
            import_ids_provider=metadata.referral_history_import_ids,
        ),
        metadata_repository=metadata,
        engine=ReferralForecastEngine(
            tracker=tracker,
            horizon_days=settings.forecast_horizon_days,
            min_train_days=settings.forecast_min_train_days,
            minimum_relative_improvement=settings.forecast_min_relative_improvement,
        ),
        uow_factory=get_unit_of_work_factory(),
    )
