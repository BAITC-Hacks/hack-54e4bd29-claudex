from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.business.forecasting.contracts import (
    DailyReferralCount,
    ForecastEngineResult,
    ForecastMetricSet,
    ForecastPointResult,
    ReferralDatasetWatermark,
)
from app.business.forecasting.service import ForecastQueryService, ForecastTrainingService
from app.core.exceptions import NotFoundError
from app.models.enums import DataScopeType
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role, SecurityContext


class FakeHistory:
    def daily_global(self) -> tuple[DailyReferralCount, ...]:
        start = date(2025, 1, 1)
        return tuple(
            DailyReferralCount(start + timedelta(days=index), 100 + index % 7)
            for index in range(70)
        )


class FakeMetadata:
    def referral_watermark(self) -> ReferralDatasetWatermark:
        return ReferralDatasetWatermark(
            completed_at=datetime(2025, 4, 1, tzinfo=UTC),
            import_ids=(uuid.UUID("00000000-0000-0000-0000-000000000001"),),
            file_hashes=("a" * 64,),
        )


class FakeEngine:
    def __init__(self) -> None:
        self.calls = 0

    def train(self, history, watermark, *, generated_at):
        del history, watermark
        self.calls += 1
        return ForecastEngineResult(
            generated_at=generated_at,
            input_period_start=date(2025, 1, 1),
            input_period_end=date(2025, 3, 11),
            training_rows=70,
            feature_schema_version="referrals_daily_v1",
            selected_model="weekly_naive",
            selected_model_type="BASELINE",
            model_version=f"referrals-global-20250311-test-{self.calls}",
            mlflow_run_id=f"run-{self.calls}",
            metrics=ForecastMetricSet(3.0, 0.02, 4.0),
            strongest_baseline="weekly_naive",
            baseline_metrics=ForecastMetricSet(3.0, 0.02, 4.0),
            validation_folds=({"index": 1},),
            candidate_metrics=({"model": "weekly_naive", "mae": 3.0},),
            selection_rationale="baseline retained",
            points=tuple(
                ForecastPointResult(
                    forecast_date=date(2025, 3, 11) + timedelta(days=index),
                    predicted_value=100.0,
                    baseline_value=100.0,
                )
                for index in range(1, 8)
            ),
        )


class FakeForecastRepository:
    def __init__(self) -> None:
        self.runs = []
        self.points = []

    def add(self, forecast):
        self.runs.append(forecast)
        return forecast

    def add_points(self, points):
        self.points.extend(points)
        return len(points)

    def latest_global(self, target):
        del target
        return self.runs[-1] if self.runs else None

    def points_for(self, forecast_id):
        return tuple(item for item in self.points if item.forecast_id == forecast_id)


class FakeModelVersionRepository:
    def __init__(self) -> None:
        self.items = []

    def add(self, model_version):
        self.items.append(model_version)
        return model_version


class FakeUow:
    def __init__(self, forecasts, model_versions) -> None:
        self.forecasts = forecasts
        self.model_versions = model_versions
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def commit(self) -> None:
        self.commits += 1


def _context(role: Role, *, global_scope: bool) -> SecurityContext:
    return SecurityContext(
        user_id="test",
        roles=frozenset({role}),
        scope=DataScope.global_scope() if global_scope else DataScope(resolved=True),
    )


def test_training_persists_model_run_points_and_watermark_atomically() -> None:
    forecasts = FakeForecastRepository()
    versions = FakeModelVersionRepository()
    uow = FakeUow(forecasts, versions)
    service = ForecastTrainingService(
        history_repository=FakeHistory(),
        metadata_repository=FakeMetadata(),
        engine=FakeEngine(),
        uow_factory=lambda: uow,
        clock=lambda: datetime(2025, 4, 2, tzinfo=UTC),
    )

    forecast_id = service.run_referral_forecast()

    assert uow.commits == 1
    assert len(versions.items) == 1
    assert len(forecasts.runs) == 1
    assert len(forecasts.points) == 7
    assert forecasts.runs[0].scope_type == DataScopeType.GLOBAL
    assert forecasts.runs[0].dataset_watermark["file_hashes"] == ["a" * 64]
    assert forecasts.runs[0].id == forecast_id


def test_retraining_appends_a_new_version_without_mutating_previous_run() -> None:
    forecasts = FakeForecastRepository()
    versions = FakeModelVersionRepository()
    uow = FakeUow(forecasts, versions)
    service = ForecastTrainingService(
        history_repository=FakeHistory(),
        metadata_repository=FakeMetadata(),
        engine=FakeEngine(),
        uow_factory=lambda: uow,
        clock=lambda: datetime(2025, 4, 2, tzinfo=UTC),
    )

    first_id = service.run_referral_forecast()
    second_id = service.run_referral_forecast()

    assert first_id != second_id
    assert len(forecasts.runs) == 2
    assert len(forecasts.points) == 14
    assert len(versions.items) == 2
    assert versions.items[0].version != versions.items[1].version


def test_expired_forecast_is_returned_as_stale_with_explicit_limitation() -> None:
    forecasts = FakeForecastRepository()
    versions = FakeModelVersionRepository()
    uow = FakeUow(forecasts, versions)
    ForecastTrainingService(
        history_repository=FakeHistory(),
        metadata_repository=FakeMetadata(),
        engine=FakeEngine(),
        uow_factory=lambda: uow,
        clock=lambda: datetime(2025, 4, 2, tzinfo=UTC),
    ).run_referral_forecast()
    service = ForecastQueryService(
        uow_factory=lambda: uow,
        history_repository=FakeHistory(),
        authorization=AuthorizationService(),
        clock=lambda: datetime(2025, 4, 20, tzinfo=UTC),
    )

    result = service.latest_referral_forecast(_context(Role.ADMIN, global_scope=True))

    assert result.freshness_status == "STALE"
    assert any("период действия" in item.lower() for item in result.limitations)


def test_global_forecast_is_hidden_from_non_global_scope() -> None:
    service = ForecastQueryService(
        uow_factory=lambda: FakeUow(
            FakeForecastRepository(), FakeModelVersionRepository()
        ),
        history_repository=FakeHistory(),
        authorization=AuthorizationService(),
    )

    with pytest.raises(NotFoundError):
        service.latest_referral_forecast(
            _context(Role.REGIONAL_ANALYST, global_scope=False)
        )


def test_missing_global_forecast_is_not_rendered_as_zero() -> None:
    service = ForecastQueryService(
        uow_factory=lambda: FakeUow(
            FakeForecastRepository(), FakeModelVersionRepository()
        ),
        history_repository=FakeHistory(),
        authorization=AuthorizationService(),
    )

    with pytest.raises(NotFoundError):
        service.latest_referral_forecast(_context(Role.ADMIN, global_scope=True))


@pytest.mark.parametrize("change_after", [1, 2])
def test_training_rejects_publication_change_before_persist(change_after):
    from dataclasses import replace

    from app.core.exceptions import ConflictError

    class ChangingMetadata(FakeMetadata):
        calls = 0

        def referral_watermark(self):
            self.calls += 1
            initial = super().referral_watermark()
            return (
                initial
                if self.calls <= change_after
                else replace(initial, file_hashes=("b" * 64,))
            )

    forecasts = FakeForecastRepository()
    versions = FakeModelVersionRepository()
    uow = FakeUow(forecasts, versions)
    service = ForecastTrainingService(
        history_repository=FakeHistory(),
        metadata_repository=ChangingMetadata(),
        engine=FakeEngine(),
        uow_factory=lambda: uow,
    )
    with pytest.raises(ConflictError, match="PUBLICATION_CHANGED"):
        service.run_referral_forecast()
    assert uow.commits == 0
    assert forecasts.runs == []
    assert versions.items == []
