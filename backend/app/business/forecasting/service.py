"""Business orchestration for training and retrieving referral forecasts."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.business.forecasting.contracts import (
    ForecastPointResult,
    ReferralForecastSnapshot,
)
from app.business.forecasting.ports import (
    ForecastEnginePort,
    ForecastMetadataRepository,
    ReferralHistoryRepository,
)
from app.business.ports import UnitOfWorkFactory
from app.core.exceptions import NotFoundError
from app.models.analytics import Forecast
from app.models.enums import DataScopeType, ForecastStatus, ModelVersionStatus
from app.models.forecast_point import ForecastPoint
from app.models.model_version import ModelVersion
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.permissions import Permission

REFERRAL_TARGET = "DAILY_REFERRAL_COUNT"
FORECAST_LIMITATIONS = (
    "Прогноз основан примерно на трёх месяцах доступной истории.",
    "Годовая сезонность не подтверждена.",
    "Это расчётный краткосрочный прогноз потока направлений, а не прогноз перегрузки.",
)


class ForecastTrainingService:
    def __init__(
        self,
        *,
        history_repository: ReferralHistoryRepository,
        metadata_repository: ForecastMetadataRepository,
        engine: ForecastEnginePort,
        uow_factory: UnitOfWorkFactory,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._history = history_repository
        self._metadata = metadata_repository
        self._engine = engine
        self._uow_factory = uow_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def run_referral_forecast(self) -> uuid.UUID:
        history = self._history.daily_global()
        watermark = self._metadata.referral_watermark()
        result = self._engine.train(history, watermark, generated_at=self._clock())
        watermark_data = watermark.as_dict()
        model_version = ModelVersion(
            id=uuid.uuid4(),
            target=REFERRAL_TARGET,
            algorithm=result.selected_model,
            version=result.model_version,
            mlflow_run_id=result.mlflow_run_id,
            feature_schema_version=result.feature_schema_version,
            trained_at=result.generated_at,
            training_period_start=result.input_period_start,
            training_period_end=result.input_period_end,
            training_rows=result.training_rows,
            forecast_horizon_days=len(result.points),
            metrics=result.metrics.as_dict(),
            baseline_metrics=result.baseline_metrics.as_dict(),
            validation_config={
                "folds": list(result.validation_folds),
                "horizon_days": len(result.points),
            },
            dataset_watermark=watermark_data,
            selection_rationale=result.selection_rationale,
            status=ModelVersionStatus.SELECTED,
        )
        forecast = Forecast(
            id=uuid.uuid4(),
            hospital_id=None,
            region_id=None,
            scope_type=DataScopeType.GLOBAL,
            target=REFERRAL_TARGET,
            horizon_days=len(result.points),
            predicted_value=sum(item.predicted_value for item in result.points),
            lower_bound=None,
            upper_bound=None,
            model_version=result.model_version,
            metric_name="MAE",
            metric_value=result.metrics.mae,
            baseline_metric_name="MAE",
            baseline_metric_value=result.baseline_metrics.mae,
            input_period_start=datetime.combine(
                result.input_period_start, datetime.min.time(), UTC
            ),
            input_period_end=datetime.combine(
                result.input_period_end, datetime.max.time(), UTC
            ),
            generated_at=result.generated_at,
            status=ForecastStatus.VALID,
            invalidity_reason=None,
            assumptions=list(FORECAST_LIMITATIONS),
            model_version_id=model_version.id,
            selected_model=result.selected_model,
            baseline_model=result.strongest_baseline,
            feature_schema_version=result.feature_schema_version,
            dataset_watermark=watermark_data,
            validation_metrics=result.metrics.as_dict(),
            baseline_metrics=result.baseline_metrics.as_dict(),
            validation_folds=list(result.validation_folds),
            forecast_start=result.points[0].forecast_date,
            forecast_end=result.points[-1].forecast_date,
        )
        points = tuple(
            ForecastPoint(
                forecast_id=forecast.id,
                forecast_date=item.forecast_date,
                predicted_value=item.predicted_value,
                baseline_value=item.baseline_value,
            )
            for item in result.points
        )
        with self._uow_factory() as uow:
            uow.model_versions.add(model_version)
            uow.forecasts.add(forecast)
            uow.forecasts.add_points(points)
            uow.commit()
        return forecast.id


class ForecastQueryService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        history_repository: ReferralHistoryRepository,
        authorization: AuthorizationService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._history = history_repository
        self._authorization = authorization
        self._clock = clock or (lambda: datetime.now(UTC))

    def latest_referral_forecast(
        self, context: SecurityContext
    ) -> ReferralForecastSnapshot:
        self._authorization.require_permission(context, Permission.FORECAST_READ)
        if not context.has_global_scope:
            raise NotFoundError("Прогноз не найден")
        with self._uow_factory() as uow:
            forecast = uow.forecasts.latest_global(REFERRAL_TARGET)
            if forecast is None:
                raise NotFoundError("Прогноз не найден")
            points = uow.forecasts.points_for(forecast.id)
        history = self._history.daily_global()
        if forecast.forecast_start is None or forecast.forecast_end is None:
            raise NotFoundError("Прогноз не найден")
        is_stale = forecast.forecast_end < self._clock().date()
        limitations = tuple(forecast.assumptions)
        if is_stale:
            limitations = (
                *limitations,
                "Период действия прогноза завершён; результат показан как исторический.",
            )
        return ReferralForecastSnapshot(
            id=forecast.id,
            generated_at=forecast.generated_at,
            input_period_start=forecast.input_period_start,
            input_period_end=forecast.input_period_end,
            forecast_start=forecast.forecast_start,
            forecast_end=forecast.forecast_end,
            model_version=forecast.model_version,
            selected_model=forecast.selected_model,
            baseline_model=forecast.baseline_model,
            metrics=forecast.validation_metrics,
            baseline_metrics=forecast.baseline_metrics,
            dataset_watermark=forecast.dataset_watermark,
            freshness_status="STALE" if is_stale else "CURRENT",
            limitations=limitations,
            historical=history[-30:],
            points=tuple(
                ForecastPointResult(
                    item.forecast_date,
                    float(item.predicted_value),
                    float(item.baseline_value),
                )
                for item in points
            ),
        )
