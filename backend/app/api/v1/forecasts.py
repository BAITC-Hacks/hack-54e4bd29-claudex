"""Read-only HTTP access to persisted short-horizon forecasts."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, ForecastQueryServiceDep
from app.schemas.common import ERROR_RESPONSES
from app.schemas.forecasting import (
    HistoricalReferralPointResponse,
    ReferralForecastPointResponse,
    ReferralForecastResponse,
)

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get(
    "/referrals/latest",
    response_model=ReferralForecastResponse,
    responses=ERROR_RESPONSES,
)
def latest_referral_forecast(
    context: CurrentUser,
    service: ForecastQueryServiceDep,
) -> ReferralForecastResponse:
    result = service.latest_referral_forecast(context)
    return ReferralForecastResponse(
        id=result.id,
        target="DAILY_REFERRAL_COUNT",
        scope_type="GLOBAL",
        horizon_days=len(result.points),
        input_period_start=result.input_period_start,
        input_period_end=result.input_period_end,
        forecast_start=result.forecast_start,
        forecast_end=result.forecast_end,
        generated_at=result.generated_at,
        model_version=result.model_version,
        selected_model=result.selected_model,
        baseline_model=result.baseline_model,
        metrics=result.metrics,
        baseline_metrics=result.baseline_metrics,
        dataset_watermark=result.dataset_watermark,
        freshness_status=result.freshness_status,
        limitations=list(result.limitations),
        historical=[
            HistoricalReferralPointResponse(date=item.observed_on, value=item.count)
            for item in result.historical
        ],
        forecast=[
            ReferralForecastPointResponse(
                date=item.forecast_date,
                predicted_value=item.predicted_value,
                baseline_value=item.baseline_value,
                delta_from_baseline=item.delta_from_baseline,
            )
            for item in result.points
        ],
        disclaimer="Расчётный прогноз. Решение принимает уполномоченный сотрудник.",
    )
