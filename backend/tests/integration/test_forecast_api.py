from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.business.forecasting.contracts import (
    DailyReferralCount,
    ForecastPointResult,
    ReferralForecastSnapshot,
)
from app.composition import build_forecast_query_service
from app.core.exceptions import NotFoundError
from app.security.context import Role
from app.security.testing import make_test_token

API = "/api/v1/forecasts/referrals/latest"


class StubForecastService:
    def latest_referral_forecast(self, context) -> ReferralForecastSnapshot:
        if not context.has_global_scope:
            raise NotFoundError("Прогноз не найден")
        return ReferralForecastSnapshot(
            id=uuid.UUID("00000000-0000-0000-0000-000000000101"),
            generated_at=datetime(2025, 4, 2, tzinfo=UTC),
            input_period_start=datetime(2025, 1, 1, tzinfo=UTC),
            input_period_end=datetime(2025, 3, 31, tzinfo=UTC),
            validation_period_start=date(2025, 2, 12),
            validation_period_end=date(2025, 3, 25),
            forecast_start=date(2025, 4, 1),
            forecast_end=date(2025, 4, 7),
            model_version="referrals-global-v1",
            selected_model="weekly_naive",
            baseline_model="weekly_naive",
            metrics={"mae": 3.0, "wape": 0.02, "rmse": 4.0},
            baseline_metrics={"mae": 3.0, "wape": 0.02, "rmse": 4.0},
            dataset_watermark={"import_ids": ["import-1"]},
            freshness_status="STALE",
            limitations=("Годовая сезонность не подтверждена.",),
            historical=(DailyReferralCount(date(2025, 3, 31), 100),),
            points=(ForecastPointResult(date(2025, 4, 1), 101.0, 100.0),),
        )


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    app.dependency_overrides[build_forecast_query_service] = StubForecastService
    return app


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_test_token('forecast-admin', [Role.ADMIN])}"}


def test_forecast_requires_authentication(client: TestClient) -> None:
    assert client.get(API).status_code == 401


def test_latest_referral_forecast_has_provenance_and_no_confidence_claim(
    client: TestClient,
) -> None:
    response = client.get(API, headers=auth())

    assert response.status_code == 200
    body = response.json()
    assert body["target"] == "DAILY_REFERRAL_COUNT"
    assert body["scope_type"] == "GLOBAL"
    assert body["model_version"] == "referrals-global-v1"
    assert body["validation_period_start"] == "2025-02-12"
    assert body["validation_period_end"] == "2025-03-25"
    assert body["forecast"][0] == {
        "date": "2025-04-01",
        "predicted_value": 101.0,
        "baseline_value": 100.0,
        "delta_from_baseline": 1.0,
    }
    assert body["freshness_status"] == "STALE"
    assert "confidence" not in body
    assert body["disclaimer"] == (
        "Расчётный прогноз. Решение принимает уполномоченный сотрудник."
    )


def test_global_forecast_is_not_enumerable_from_regional_scope(
    client: TestClient,
) -> None:
    headers = {
        "Authorization": (
            f"Bearer {make_test_token('forecast-regional', [Role.REGIONAL_ANALYST])}"
        )
    }

    response = client.get(API, headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
