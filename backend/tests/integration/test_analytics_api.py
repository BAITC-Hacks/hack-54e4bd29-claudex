"""Public HTTP contracts for descriptive analytics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.business.analytics.contracts import (
    AnalyticsCell,
    AnalyticsFilter,
    AnalyticsMetadata,
    OverviewResult,
)
from app.composition import build_analytics_service
from app.security.context import Role
from app.security.testing import make_test_token

API = "/api/v1/analytics"


class StubAnalyticsService:
    def overview(self, _context: object, filters: AnalyticsFilter) -> OverviewResult:
        filters.validate()
        metadata = AnalyticsMetadata(
            date_from=filters.date_from,
            date_to=filters.date_to,
            sources=("ИС БГ:REFERRALS",),
            generated_at=datetime(2026, 5, 14, tzinfo=UTC),
            completed_import_watermark=datetime(2026, 5, 13, tzinfo=UTC),
            limitations=("Сопоставление организаций неполное.",),
            latest_import_ids=("00000000-0000-0000-0000-000000000001",),
        )

        def exact(value: int) -> AnalyticsCell[int]:
            return AnalyticsCell(value=value, suppressed=False)

        return OverviewResult(
            metadata=metadata,
            referrals_total=exact(20),
            waiting_records=exact(12),
            refusals_total=exact(7),
            hospitalized_total=exact(8),
            unknown_records=exact(1),
            represented_organizations=exact(4),
            represented_regions=exact(2),
        )


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    app.dependency_overrides[build_analytics_service] = StubAnalyticsService
    return app


def auth() -> dict[str, str]:
    return {
        "Authorization": (f"Bearer {make_test_token('analytics-admin', [Role.ADMIN])}")
    }


def test_overview_requires_authentication(client: TestClient) -> None:
    assert client.get(f"{API}/overview").status_code == 401


def test_overview_has_data_and_metadata_contract(client: TestClient) -> None:
    response = client.get(f"{API}/overview", headers=auth())

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["data"]["referrals_total"] == {
        "value": 20,
        "suppressed": False,
    }
    assert body["meta"]["source"] == ["ИС БГ:REFERRALS"]
    assert body["meta"]["latest_import_id"] == ("00000000-0000-0000-0000-000000000001")
    assert body["meta"]["limitations"] == ["Сопоставление организаций неполное."]


def test_oversized_analytics_period_is_rejected(client: TestClient) -> None:
    response = client.get(
        f"{API}/overview?date_from=2024-01-01T00:00:00Z&" "date_to=2025-03-31T23:59:59Z",
        headers=auth(),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_organization_reference_is_rejected(client: TestClient) -> None:
    response = client.get(f"{API}/organizations/not-a-safe-reference", headers=auth())

    assert response.status_code == 422


def test_organization_page_size_is_bounded(client: TestClient) -> None:
    response = client.get(f"{API}/organizations?page_size=1000000", headers=auth())

    assert response.status_code == 422
