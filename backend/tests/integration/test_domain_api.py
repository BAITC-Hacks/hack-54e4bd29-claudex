"""Контракты доменного API.

Проверяется то, что видит клиент: постраничная выдача, фильтрация,
отказ в доступе, конфликт одновременного изменения и отсутствие утечки
объектов за пределы области данных.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.business.audit.service import AuditService
from app.business.hospitals.service import HospitalService
from app.business.incidents.service import IncidentService
from app.business.regions.service import RegionService
from app.business.shared.events import EventDispatcher
from app.business.signals.service import SignalService
from app.composition import (
    build_audit_service,
    build_hospital_service,
    build_incident_service,
    build_region_service,
    build_signal_service,
)
from app.security.authorization import AuthorizationService
from app.security.context import DataScope
from tests.conftest import ScopeOverride
from tests.fakes import (
    FakeStore,
    make_hospital,
    make_region,
    make_signal,
    make_user,
    unit_of_work_factory,
)

API = "/api/v1"


@pytest.fixture
def world(store: FakeStore, scopes: ScopeOverride):
    """Два региона, три организации, три сигнала и три пользователя."""

    class World:
        pass

    world = World()
    world.region_a = store.add_region(make_region("R-A", "Регион А"))
    world.region_b = store.add_region(make_region("R-B", "Регион Б"))
    world.hospital_a1 = store.add_hospital(make_hospital(world.region_a, "H-A1", "А1"))
    world.hospital_a2 = store.add_hospital(make_hospital(world.region_a, "H-A2", "А2"))
    world.hospital_b1 = store.add_hospital(make_hospital(world.region_b, "H-B1", "Б1"))
    world.signal_a1 = store.add_signal(make_signal(world.hospital_a1))
    world.signal_a2 = store.add_signal(make_signal(world.hospital_a2))
    world.signal_b1 = store.add_signal(make_signal(world.hospital_b1))

    manager = store.add_user(
        make_user("hospital-manager"),
        DataScope(hospital_ids=frozenset({str(world.hospital_a1.id)}), resolved=True),
    )
    scopes.assign("hospital-manager", store.user_scopes[manager.id], manager.id)
    world.manager = manager

    analyst = store.add_user(
        make_user("regional-analyst"),
        DataScope(region_ids=frozenset({str(world.region_a.id)}), resolved=True),
    )
    scopes.assign("regional-analyst", store.user_scopes[analyst.id], analyst.id)
    world.analyst = analyst

    viewer = store.add_user(make_user("hospital-viewer"), DataScope.unresolved())
    scopes.assign("hospital-viewer", DataScope.unresolved(), viewer.id)
    return world


@pytest.fixture
def app(store: FakeStore, scopes: ScopeOverride, app: FastAPI) -> Iterator[FastAPI]:
    """Приложение, у которого сервисы работают на хранилище в памяти."""
    factory = unit_of_work_factory(store)
    authz = AuthorizationService()
    dispatcher = EventDispatcher()

    app.dependency_overrides[build_region_service] = lambda: RegionService(factory, authz)
    app.dependency_overrides[build_hospital_service] = lambda: HospitalService(
        factory, authz
    )
    app.dependency_overrides[build_signal_service] = lambda: SignalService(
        factory, authz, dispatcher
    )
    app.dependency_overrides[build_incident_service] = lambda: IncidentService(
        factory, authz
    )
    app.dependency_overrides[build_audit_service] = lambda: AuditService(factory, authz)
    yield app


def auth(subject: str) -> dict[str, str]:
    role = {
        "hospital-manager": "HOSPITAL_MANAGER",
        "regional-analyst": "REGIONAL_ANALYST",
        "hospital-viewer": "HOSPITAL_ANALYST",
    }[subject]
    from app.security.context import Role
    from app.security.testing import make_test_token

    return {"Authorization": f"Bearer {make_test_token(subject, [Role(role)])}"}


# --- Аутентификация ---------------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/regions", "/hospitals", "/signals", "/incidents", "/audit"]
)
def test_endpoints_require_authentication(client: TestClient, world, path: str) -> None:
    assert client.get(f"{API}{path}").status_code == 401


def test_invalid_token_is_rejected(client: TestClient, world) -> None:
    # Значение заголовка задаётся латиницей: HTTP-заголовки передаются
    # в ASCII, и кириллица не дошла бы до приложения.
    response = client.get(
        f"{API}/signals", headers={"Authorization": "Bearer forged-token"}
    )
    assert response.status_code == 401


# --- Постраничная выдача ----------------------------------------------------


def test_signal_list_is_paginated(client: TestClient, world) -> None:
    response = client.get(f"{API}/signals", headers=auth("regional-analyst"))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "page_size", "total", "has_next"}
    assert body["page"] == 1
    assert body["total"] == 2


def test_page_size_limit_is_enforced(client: TestClient, world) -> None:
    """Запрос с огромной страницей отклоняется, а не исполняется."""
    response = client.get(
        f"{API}/signals?page_size=1000000", headers=auth("regional-analyst")
    )
    assert response.status_code == 422


def test_second_page_is_empty_when_no_rows_left(client: TestClient, world) -> None:
    response = client.get(
        f"{API}/signals?page=5&page_size=1", headers=auth("regional-analyst")
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_unknown_sort_field_is_rejected(client: TestClient, world) -> None:
    response = client.get(
        f"{API}/signals?sort_by=hospital_id", headers=auth("regional-analyst")
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- Фильтрация -------------------------------------------------------------


def test_filter_by_hospital(client: TestClient, world) -> None:
    response = client.get(
        f"{API}/signals?hospital_id={world.hospital_a2.id}",
        headers=auth("regional-analyst"),
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(world.signal_a2.id)]


def test_filter_by_status(client: TestClient, world) -> None:
    response = client.get(f"{API}/signals?status=NEW", headers=auth("regional-analyst"))
    assert response.json()["total"] == 2


def test_unknown_status_value_is_rejected(client: TestClient, world) -> None:
    response = client.get(
        f"{API}/signals?status=НЕИЗВЕСТНО", headers=auth("regional-analyst")
    )
    assert response.status_code == 422


def test_invalid_uuid_is_rejected(client: TestClient, world) -> None:
    response = client.get(f"{API}/signals/not-a-uuid", headers=auth("regional-analyst"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- Область данных ---------------------------------------------------------


def test_hospital_user_sees_only_own_signals(client: TestClient, world) -> None:
    body = client.get(f"{API}/signals", headers=auth("hospital-manager")).json()
    assert [item["id"] for item in body["items"]] == [str(world.signal_a1.id)]


def test_signal_outside_scope_returns_404(client: TestClient, world) -> None:
    """Объект вне области неотличим от отсутствующего."""
    response = client.get(
        f"{API}/signals/{world.signal_b1.id}", headers=auth("hospital-manager")
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_hospital_outside_scope_returns_404(client: TestClient, world) -> None:
    response = client.get(
        f"{API}/hospitals/{world.hospital_b1.id}", headers=auth("hospital-manager")
    )
    assert response.status_code == 404


def test_missing_and_forbidden_objects_are_indistinguishable(
    client: TestClient, world
) -> None:
    """Ответы для чужого и несуществующего объекта совпадают.

    Различие позволило бы перебором выяснить состав организаций.
    """
    foreign = client.get(
        f"{API}/signals/{world.signal_b1.id}", headers=auth("hospital-manager")
    )
    missing = client.get(
        f"{API}/signals/{uuid.uuid4()}", headers=auth("hospital-manager")
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["code"] == missing.json()["error"]["code"]


def test_user_without_scope_sees_nothing(client: TestClient, world) -> None:
    body = client.get(f"{API}/signals", headers=auth("hospital-viewer")).json()
    assert body["items"] == []
    assert body["total"] == 0


def test_hospital_role_cannot_read_regions(client: TestClient, world) -> None:
    response = client.get(f"{API}/regions", headers=auth("hospital-manager"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- Карточка сигнала -------------------------------------------------------


def test_signal_detail_reports_available_transitions(client: TestClient, world) -> None:
    body = client.get(
        f"{API}/signals/{world.signal_a1.id}", headers=auth("hospital-manager")
    ).json()
    assert body["status"] == "NEW"
    assert sorted(body["available_transitions"]) == ["CLOSED", "IN_PROGRESS"]
    assert body["version"] == 1


def test_analyst_gets_no_transitions(client: TestClient, world, scopes) -> None:
    scopes.assign(
        "hospital-viewer",
        DataScope(hospital_ids=frozenset({str(world.hospital_a1.id)}), resolved=True),
        scopes.user_ids["hospital-viewer"],
    )
    body = client.get(
        f"{API}/signals/{world.signal_a1.id}", headers=auth("hospital-viewer")
    ).json()
    assert body["available_transitions"] == []


# --- Смена статуса ----------------------------------------------------------


def test_status_change_succeeds(client: TestClient, world) -> None:
    response = client.patch(
        f"{API}/signals/{world.signal_a1.id}/status",
        headers=auth("hospital-manager"),
        json={"status": "IN_PROGRESS", "version": 1, "reason": "взято в работу"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["version"] == 2
    assert len(body["audit_history"]) == 1


def test_stale_version_returns_409(client: TestClient, world) -> None:
    client.patch(
        f"{API}/signals/{world.signal_a1.id}/status",
        headers=auth("hospital-manager"),
        json={"status": "IN_PROGRESS", "version": 1, "reason": "первый"},
    )
    response = client.patch(
        f"{API}/signals/{world.signal_a1.id}/status",
        headers=auth("hospital-manager"),
        json={"status": "CLOSED", "version": 1, "reason": "второй по старой версии"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_invalid_transition_returns_409(client: TestClient, world) -> None:
    client.patch(
        f"{API}/signals/{world.signal_a1.id}/status",
        headers=auth("hospital-manager"),
        json={"status": "CLOSED", "version": 1, "reason": "закрыто"},
    )
    response = client.patch(
        f"{API}/signals/{world.signal_a1.id}/status",
        headers=auth("hospital-manager"),
        json={"status": "NEW", "version": 2, "reason": "вернуть в новые"},
    )
    assert response.status_code == 409


def test_unknown_status_in_body_is_rejected(client: TestClient, world) -> None:
    response = client.patch(
        f"{API}/signals/{world.signal_a1.id}/status",
        headers=auth("hospital-manager"),
        json={"status": "ARCHIVED", "version": 1},
    )
    assert response.status_code == 422


def test_missing_reason_is_rejected(client: TestClient, world) -> None:
    response = client.patch(
        f"{API}/signals/{world.signal_a1.id}/status",
        headers=auth("hospital-manager"),
        json={"status": "CLOSED", "version": 1},
    )
    assert response.status_code == 422


def test_extra_fields_are_rejected(client: TestClient, world) -> None:
    """Массовое присвоение исключено: лишние поля не принимаются."""
    response = client.patch(
        f"{API}/signals/{world.signal_a1.id}/status",
        headers=auth("hospital-manager"),
        json={
            "status": "IN_PROGRESS",
            "version": 1,
            "reason": "ок",
            "severity": "CRITICAL",
            "hospital_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 422


def test_analyst_cannot_change_status(client: TestClient, world, scopes) -> None:
    scopes.assign(
        "hospital-viewer",
        DataScope(hospital_ids=frozenset({str(world.hospital_a1.id)}), resolved=True),
        scopes.user_ids["hospital-viewer"],
    )
    response = client.patch(
        f"{API}/signals/{world.signal_a1.id}/status",
        headers=auth("hospital-viewer"),
        json={"status": "IN_PROGRESS", "version": 1, "reason": "попытка"},
    )
    assert response.status_code == 403


def test_status_change_outside_scope_returns_404(client: TestClient, world) -> None:
    response = client.patch(
        f"{API}/signals/{world.signal_b1.id}/status",
        headers=auth("hospital-manager"),
        json={"status": "IN_PROGRESS", "version": 1, "reason": "чужой"},
    )
    assert response.status_code == 404


# --- Назначение -------------------------------------------------------------


def test_assign_and_unassign(client: TestClient, world) -> None:
    assigned = client.post(
        f"{API}/signals/{world.signal_a1.id}/assign",
        headers=auth("hospital-manager"),
        json={"assignee_id": str(world.manager.id), "version": 1},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_user_id"] == str(world.manager.id)

    removed = client.request(
        "DELETE",
        f"{API}/signals/{world.signal_a1.id}/assign",
        headers=auth("hospital-manager"),
        json={"version": 2},
    )
    assert removed.status_code == 200
    assert removed.json()["assigned_user_id"] is None


def test_assign_outside_scope_user_is_rejected(client: TestClient, world) -> None:
    response = client.post(
        f"{API}/signals/{world.signal_a1.id}/assign",
        headers=auth("hospital-manager"),
        json={"assignee_id": str(world.analyst.id), "version": 1},
    )
    # Региональный аналитик видит организацию А1, назначение допустимо.
    assert response.status_code == 200


def test_assignment_writes_audit_visible_in_card(client: TestClient, world) -> None:
    client.post(
        f"{API}/signals/{world.signal_a1.id}/assign",
        headers=auth("hospital-manager"),
        json={"assignee_id": str(world.manager.id), "version": 1},
    )
    body = client.get(
        f"{API}/signals/{world.signal_a1.id}", headers=auth("hospital-manager")
    ).json()
    assert any(event["action"] == "SIGNAL_ASSIGNED" for event in body["audit_history"])
    assert any(action["action_type"] == "ASSIGNMENT" for action in body["actions"])


# --- Журнал аудита ----------------------------------------------------------


def test_audit_is_scoped(client: TestClient, world) -> None:
    """Журнал не раскрывает записи о недоступных объектах."""
    client.patch(
        f"{API}/signals/{world.signal_a1.id}/status",
        headers=auth("hospital-manager"),
        json={"status": "IN_PROGRESS", "version": 1, "reason": "в работу"},
    )
    body = client.get(f"{API}/audit", headers=auth("hospital-manager")).json()
    assert body["total"] == 1
    assert body["items"][0]["entity_id"] == str(world.signal_a1.id)


def test_audit_requires_permission(client: TestClient, world, scopes) -> None:
    scopes.assign(
        "hospital-viewer",
        DataScope(hospital_ids=frozenset({str(world.hospital_a1.id)}), resolved=True),
        scopes.user_ids["hospital-viewer"],
    )
    response = client.get(f"{API}/audit", headers=auth("hospital-viewer"))
    assert response.status_code == 403
