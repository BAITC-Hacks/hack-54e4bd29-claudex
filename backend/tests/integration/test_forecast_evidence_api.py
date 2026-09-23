"""Read persisted canonical forecast evidence without global history leakage."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.business.forecasting.service import ForecastQueryService
from app.composition import build_forecast_query_service
from app.models.enums import DataScopeType
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role
from app.security.testing import make_test_token
from tests.fakes import make_hospital, make_region, make_user, unit_of_work_factory


@pytest.fixture
def evidence(app, store, scopes):
    region = store.add_region(make_region())
    hospital = store.add_hospital(make_hospital(region))
    other = store.add_hospital(make_hospital(region, "H-OTHER"))
    identifier = uuid4()
    metrics = {"mae": 2.0, "wape": 0.2, "rmse": 3.0}
    record = SimpleNamespace(
        id=identifier,
        hospital_id=hospital.id,
        region_id=None,
        scope_type=DataScopeType.HOSPITAL,
        target="DAILY_REFERRAL_COUNT",
        status="VALID",
        forecast_start=date(2025, 4, 1),
        forecast_end=date(2025, 4, 7),
        generated_at=datetime(2025, 4, 1, tzinfo=UTC),
        input_period_start=datetime(2025, 1, 1, tzinfo=UTC),
        input_period_end=datetime(2025, 3, 31, tzinfo=UTC),
        assumptions=["Synthetic historical evidence"],
        model_version="synthetic-v1",
        selected_model="synthetic",
        baseline_model="weekly_naive",
        validation_metrics=metrics,
        baseline_metrics=metrics,
        dataset_watermark={"mapping_version": "synthetic-mapping-v1"},
    )
    store.forecasts[identifier] = record
    factory = unit_of_work_factory(store)

    class History:
        def daily_global(self):
            raise AssertionError("by-ID reading must not query unrelated global history")

    def uow_factory():
        uow = factory()
        uow.forecasts.points_for = lambda _: [
            SimpleNamespace(
                forecast_date=date(2025, 4, 1), predicted_value=10.0, baseline_value=9.0
            )
        ]
        return uow

    service = ForecastQueryService(
        uow_factory=uow_factory,
        history_repository=History(),
        authorization=AuthorizationService(),
        clock=lambda: datetime(2026, 9, 23, tzinfo=UTC),
        mapping_is_current=lambda version: version == record.current_mapping_version,
    )
    record.current_mapping_version = "synthetic-mapping-v1"
    app.dependency_overrides[build_forecast_query_service] = lambda: service
    for subject, target in [("allowed", hospital), ("denied", other)]:
        scope = DataScope(hospital_ids=frozenset({str(target.id)}), resolved=True)
        user = store.add_user(make_user(subject), scope)
        scopes.assign(subject, scope, user.id)
    return record


def headers(subject):
    return {"Authorization": f"Bearer {make_test_token(subject,[Role.HOSPITAL_ANALYST])}"}


def test_scoped_forecast_has_saved_provenance_and_historical_freshness(client, evidence):
    response = client.get(f"/api/v1/forecasts/{evidence.id}", headers=headers("allowed"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["scope_type"] == "HOSPITAL"
    assert payload["hospital_id"] == str(evidence.hospital_id)
    assert payload["freshness_status"] == "STALE"
    assert payload["historical"] == []
    assert payload["dataset_watermark"]["mapping_version"] == "synthetic-mapping-v1"


def test_scoped_forecast_is_hidden_and_requires_authentication(client, evidence):
    assert (
        client.get(
            f"/api/v1/forecasts/{evidence.id}", headers=headers("denied")
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/forecasts/{evidence.id}").status_code == 401
    assert (
        client.get("/api/v1/forecasts/not-a-uuid", headers=headers("allowed")).status_code
        == 422
    )


def test_invalid_saved_result_cannot_be_displayed_as_valid(client, evidence):
    evidence.status = "INVALID"
    assert (
        client.get(
            f"/api/v1/forecasts/{evidence.id}", headers=headers("allowed")
        ).status_code
        == 404
    )


def test_revoked_mapping_hides_previously_saved_forecast(client, evidence):
    evidence.current_mapping_version = None
    assert (
        client.get(
            f"/api/v1/forecasts/{evidence.id}", headers=headers("allowed")
        ).status_code
        == 404
    )
