"""Protected monitoring uses existing human workflow, never research replay state."""

from __future__ import annotations

import uuid

import pytest

from app.business.incidents.service import IncidentService
from app.business.shared.events import EventDispatcher
from app.business.signals.service import SignalService
from app.composition import build_incident_service, build_signal_service
from app.models.enums import DataScopeType
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role
from app.security.testing import make_test_token
from tests.fakes import (
    make_hospital,
    make_region,
    make_signal,
    make_user,
    unit_of_work_factory,
)

API = "/api/v1"


@pytest.fixture
def monitoring_world(app, store, scopes):
    region = store.add_region(make_region())
    hospital = store.add_hospital(make_hospital(region))
    local = store.add_signal(make_signal(hospital))
    global_signal = store.add_signal(make_signal(hospital))
    global_signal.scope_type = DataScopeType.GLOBAL
    global_signal.hospital_id = None
    global_signal.hospital = None
    factory = unit_of_work_factory(store)
    authz = AuthorizationService()
    app.dependency_overrides[build_signal_service] = lambda: SignalService(
        factory, authz, EventDispatcher()
    )
    app.dependency_overrides[build_incident_service] = lambda: IncidentService(
        factory, authz
    )
    for role in Role:
        subject = role.value.lower()
        scope = (
            DataScope.global_scope()
            if role == Role.ADMIN
            else DataScope(hospital_ids=frozenset({str(hospital.id)}), resolved=True)
        )
        user = store.add_user(make_user(subject), scope)
        scopes.assign(subject, scope, user.id)
    return local, global_signal


def auth(role):
    return {"Authorization": f"Bearer {make_test_token(role.value.lower(), [role])}"}


@pytest.mark.parametrize(
    "role",
    [
        Role.HEALTH_AUTHORITY,
        Role.REGIONAL_ANALYST,
        Role.HOSPITAL_MANAGER,
        Role.HOSPITAL_ANALYST,
    ],
)
def test_source_global_signal_cannot_be_enumerated_by_restricted_identity(
    client, monitoring_world, role, store
):
    _, signal = monitoring_world
    before = len(store.audit)
    response = client.get(f"{API}/signals/{signal.id}", headers=auth(role))
    assert response.status_code == 404
    listed = client.get(f"{API}/signals?scope_type=GLOBAL", headers=auth(role))
    assert listed.status_code == 200
    assert listed.json()["total"] == 0
    assert len(store.audit) == before


def test_observer_cannot_acknowledge_or_create_incident(client, monitoring_world, store):
    signal, _ = monitoring_world
    details = client.get(
        f"{API}/signals/{signal.id}", headers=auth(Role.HOSPITAL_ANALYST)
    )
    assert details.status_code == 200
    assert details.json()["available_transitions"] == []
    assert (
        client.post(
            f"{API}/signals/{signal.id}/acknowledge",
            headers=auth(Role.HOSPITAL_ANALYST),
            json={"version": 1, "reason": "Synthetic test"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{API}/signals/{signal.id}/incidents",
            headers=auth(Role.HOSPITAL_ANALYST),
            json={"signal_version": 1, "title": "Synthetic test"},
        ).status_code
        == 403
    )
    assert not store.incidents
    assert not store.audit


def test_human_workflow_retry_conflict_and_request_audit(client, monitoring_world, store):
    signal, _ = monitoring_world
    headers = {**auth(Role.HOSPITAL_MANAGER), "X-Request-ID": "synthetic-workflow"}
    first = client.post(
        f"{API}/signals/{signal.id}/acknowledge",
        headers=headers,
        json={"version": 1, "reason": "Synthetic reviewed evidence"},
    )
    assert first.status_code == 200
    retry = client.post(
        f"{API}/signals/{signal.id}/acknowledge",
        headers=headers,
        json={"version": 1, "reason": "Synthetic duplicate"},
    )
    assert retry.status_code == 409
    audits = [event for event in store.audit if event.entity_id == signal.id]
    assert len(audits) == 1
    assert audits[0].action == "SIGNAL_ACKNOWLEDGED"
    assert audits[0].request_id == "synthetic-workflow"
    created = client.post(
        f"{API}/signals/{signal.id}/incidents",
        headers=headers,
        json={"signal_version": 2, "title": "Synthetic human decision"},
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]
    # A new GET reads persisted domain state, not browser/replay JSON state.
    refreshed = client.get(f"{API}/incidents/{incident_id}", headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["signals"][0]["id"] == str(signal.id)
    assert len(store.incidents) == 1
    assert client.get(f"{API}/signals/{signal.id}").status_code == 401
    assert client.get(f"{API}/signals/{uuid.uuid4()}", headers=headers).status_code == 404
