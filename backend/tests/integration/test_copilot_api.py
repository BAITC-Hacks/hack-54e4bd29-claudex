"""HTTP-контракт Copilot и изоляция от обычной карточки сигнала."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.business.analytics.contracts import (
    AnalyticsCell,
    AnalyticsMetadata,
    OverviewResult,
)
from app.business.copilot.service import CopilotService
from app.business.shared.events import EventDispatcher
from app.business.signals.service import SignalService
from app.composition import (
    build_analytics_service,
    build_copilot_service,
    build_signal_service,
)
from app.core.exceptions import CopilotProviderTimeoutError
from app.models.enums import ExplanationGenerator
from app.models.signal import SignalExplanation
from app.security.authorization import AuthorizationService
from app.security.context import Role
from app.security.testing import make_test_token
from tests.fakes import (
    FakeStore,
    make_hospital,
    make_region,
    make_signal,
    unit_of_work_factory,
)


def _auth(role: Role) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_test_token('copilot-test', [role])}"}


class Provider:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    def explain(self, payload: dict[str, object]) -> dict[str, object]:  # noqa: ARG002
        self.calls += 1
        if self.fail:
            raise CopilotProviderTimeoutError()
        return {
            "explanation": (
                "Сработало правило роста очереди. Синтетический показатель "
                "подтверждает изменение, но не устанавливает его причину."
            ),
            "fact_ids": ["F1"],
        }


def test_endpoint_access_and_regular_signal_stays_available(
    app: FastAPI, client: TestClient, store: FakeStore
) -> None:
    region = store.add_region(make_region("S", "Синтетический регион"))
    hospital = store.add_hospital(make_hospital(region, "S", "Синтетическая МО"))
    signal = store.add_signal(make_signal(hospital))
    signal.source = "SYNTHETIC_DEV_SEED"
    signal.rule_version = "seed-0.1"
    signal.rule_config = {"synthetic": True}
    signal.evidence = {"synthetic": True}
    signal.data_watermark = {"synthetic": True}
    signal.explanation = SignalExplanation(
        signal_id=signal.id,
        summary="Синтетическое алгоритмическое объяснение",
        factors=[
            {"metric_code": "queue_size", "direction": "INCREASE", "change_pct": 21.0}
        ],
        caveats=[],
        generator=ExplanationGenerator.STATISTICAL,
        generator_version="seed-0.1",
        input_period_start=datetime(2025, 1, 1, tzinfo=UTC),
        input_period_end=datetime(2025, 1, 28, tzinfo=UTC),
        generated_at=datetime(2025, 1, 29, tzinfo=UTC),
    )
    factory = unit_of_work_factory(store)
    signals = SignalService(factory, AuthorizationService(), EventDispatcher())
    provider = Provider()
    app.dependency_overrides[build_copilot_service] = lambda: CopilotService(
        signals=signals,
        provider=provider,
        enabled=True,
        synthetic_demo_environment=True,
    )
    app.dependency_overrides[build_signal_service] = lambda: signals
    body = {"signal_id": str(signal.id)}

    assert client.post("/api/v1/copilot/explain-signal", json=body).status_code == 401
    assert provider.calls == 0
    assert (
        client.post(
            "/api/v1/copilot/explain-signal",
            json=body,
            headers=_auth(Role.HOSPITAL_ANALYST),
        ).status_code
        == 404
    )
    assert provider.calls == 0

    response = client.post(
        "/api/v1/copilot/explain-signal", json=body, headers=_auth(Role.ADMIN)
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["signal_id"] == str(signal.id)
    assert data["signal_version"] == 1
    assert data["facts"][0]["value"] == 21.0
    assert data["evaluation_period_start"] is None
    assert data["data_watermark_at"] is None
    assert data["request_id"] == response.headers["X-Request-ID"]
    assert data["llm_generated"] is True
    assert provider.calls == 1

    provider.fail = True
    timeout = client.post(
        "/api/v1/copilot/explain-signal", json=body, headers=_auth(Role.ADMIN)
    )
    assert timeout.status_code == 504
    assert timeout.json()["error"]["code"] == "COPILOT_PROVIDER_TIMEOUT"
    regular = client.get(f"/api/v1/signals/{signal.id}", headers=_auth(Role.ADMIN))
    assert regular.status_code == 200
    assert regular.json()["explanation"]["summary"] == (
        "Синтетическое алгоритмическое объяснение"
    )

    class AnalyticsStub:
        def overview(self, _context, filters):
            metadata = AnalyticsMetadata(
                date_from=filters.date_from,
                date_to=filters.date_to,
                sources=("SYNTHETIC",),
                generated_at=datetime.now(tz=UTC),
                completed_import_watermark=None,
                limitations=("synthetic test",),
            )
            zero = AnalyticsCell(value=0, suppressed=False)
            return OverviewResult(metadata, zero, zero, zero, zero, zero, zero, zero)

    app.dependency_overrides[build_analytics_service] = lambda: AnalyticsStub()
    analytics = client.get("/api/v1/analytics/overview", headers=_auth(Role.ADMIN))
    assert analytics.status_code == 200
    assert analytics.json()["data"]["referrals_total"]["value"] == 0

    unknown = client.post(
        "/api/v1/copilot/explain-signal",
        json={"signal_id": str(uuid.uuid4())},
        headers=_auth(Role.ADMIN),
    )
    assert unknown.status_code == 404
    assert provider.calls == 2

    app.dependency_overrides[build_copilot_service] = lambda: CopilotService(
        signals=signals,
        provider=provider,
        enabled=False,
        synthetic_demo_environment=True,
    )
    disabled = client.post(
        "/api/v1/copilot/explain-signal", json=body, headers=_auth(Role.ADMIN)
    )
    assert disabled.status_code == 503
    assert disabled.json()["error"]["code"] == "COPILOT_DISABLED"
    assert provider.calls == 2


def test_request_rejects_client_supplied_evidence(client: TestClient) -> None:
    response = client.post(
        "/api/v1/copilot/explain-signal",
        json={"signal_id": str(uuid.uuid4()), "evidence": {"fake": True}},
        headers=_auth(Role.ADMIN),
    )
    assert response.status_code == 422
