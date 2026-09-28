from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.business.simulation.service import ScenarioService
from app.composition import build_scenario_service
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role
from app.security.testing import make_test_token
from app.shared.analytics_contracts import (
    AnalyticsCell,
    AnalyticsMetadata,
    Granularity,
    MetricName,
    TimeSeriesPoint,
    TimeSeriesResult,
)
from tests.fakes import FakeStore, make_user, unit_of_work_factory

API = "/api/v1/scenarios"


class StubAnalytics:
    def referral_timeseries(self, context, filters) -> TimeSeriesResult:
        _ = context
        return TimeSeriesResult(
            metadata=AnalyticsMetadata(
                date_from=filters.date_from,
                date_to=filters.date_to,
                sources=("ИС БГ:REFERRALS",),
                generated_at=datetime(2025, 4, 1, tzinfo=UTC),
                completed_import_watermark=datetime(2025, 3, 31, tzinfo=UTC),
                limitations=("Hospital mapping incomplete.",),
                granularity=Granularity.DAY,
                latest_import_ids=("import-1",),
            ),
            metric=MetricName.REFERRALS_TOTAL,
            points=(
                TimeSeriesPoint(
                    filters.date_from,
                    filters.date_to,
                    AnalyticsCell(value=100, suppressed=False),
                ),
            ),
        )


@pytest.fixture
def scenario_client(app, scopes, store: FakeStore):
    actor = make_user("scenario-admin")
    store.add_user(actor, DataScope.global_scope())
    scopes.assign("scenario-admin", DataScope.global_scope(), actor.id)
    service = ScenarioService(
        uow_factory=unit_of_work_factory(store),
        analytics=StubAnalytics(),
        authorization=AuthorizationService(),
        clock=lambda: datetime(2026, 9, 17, tzinfo=UTC),
    )
    app.dependency_overrides[build_scenario_service] = lambda: service
    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, store
    app.dependency_overrides.pop(build_scenario_service, None)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_test_token('scenario-admin', [Role.ADMIN])}"}


def _payload() -> dict[str, object]:
    return {
        "scenario_type": "REFERRAL_INFLOW_CHANGE",
        "scope_type": "GLOBAL",
        "baseline_type": "OBSERVED",
        "assumption_value": "0.20",
        "period_start": "2025-01-01",
        "period_end": "2025-03-31",
        "historical_analysis": True,
    }


def test_preview_create_retry_get_and_list(scenario_client) -> None:
    client, store = scenario_client
    preview = client.post(f"{API}/preview", headers=_headers(), json=_payload())
    assert preview.status_code == 200
    assert preview.json()["calculated_value"] == "120.0000"
    assert preview.json()["id"] is None
    assert store.scenarios == {}

    request_id = str(uuid.uuid4())
    payload = {**_payload(), "client_request_id": request_id}
    first = client.post(API, headers=_headers(), json=payload)
    retry = client.post(API, headers=_headers(), json=payload)
    assert first.status_code == 201
    assert retry.status_code == 201
    assert first.json()["id"] == retry.json()["id"]
    assert len(store.audit) == 1

    scenario_id = first.json()["id"]
    assert client.get(f"{API}/{scenario_id}", headers=_headers()).status_code == 200
    listed = client.get(API, headers=_headers())
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


def test_invalid_assumption_unknown_field_and_authentication_are_rejected(
    scenario_client,
) -> None:
    client, _ = scenario_client
    unsupported = client.post(
        f"{API}/preview",
        headers=_headers(),
        json={**_payload(), "assumption_value": "0.15"},
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["error"]["code"] == "VALIDATION_ERROR"

    mass_assignment = client.post(
        f"{API}/preview",
        headers=_headers(),
        json={**_payload(), "calculated_value": 999999},
    )
    assert mass_assignment.status_code == 422
    assert client.post(f"{API}/preview", json=_payload()).status_code == 401


def test_arbitrary_sort_is_rejected(scenario_client) -> None:
    client, _ = scenario_client
    response = client.get(f"{API}?sort_by=calculated_value", headers=_headers())
    assert response.status_code == 422
