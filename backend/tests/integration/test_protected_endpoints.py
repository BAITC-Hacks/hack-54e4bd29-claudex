"""Защищённые эндпоинты и постановка фоновой задачи.

Проверяется, что защищённый эндпоинт принимает действительный токен
и отклоняет недействительный, а долгая операция получает устойчивое
состояние в хранилище до постановки в очередь (ADR-0010).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.system import OperationStatus
from app.security.context import Role
from app.security.testing import make_test_token
from tests.conftest import FakeOperationService

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Аутентификация ---------------------------------------------------------


def test_valid_token_is_accepted(client: TestClient) -> None:
    response = client.get(f"{API}/system/whoami", headers=auth("test:admin"))

    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["ADMIN"]
    assert body["has_global_scope"] is True


def test_request_without_token_is_rejected(client: TestClient) -> None:
    assert client.get(f"{API}/system/whoami").status_code == 401


@pytest.mark.parametrize(
    "token",
    ["invalid", "test:", "test:not-json", "eyJhbGciOiJub25lIn0.eyJzdWIiOiJhIn0."],
)
def test_invalid_token_is_rejected(client: TestClient, token: str) -> None:
    response = client.get(f"{API}/system/whoami", headers=auth(token))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_malformed_authorization_scheme_is_rejected(client: TestClient) -> None:
    response = client.get(
        f"{API}/system/whoami", headers={"Authorization": "Basic dXNlcjpwYXNz"}
    )
    assert response.status_code == 401


def test_scope_is_not_resolved_in_phase_one(client: TestClient) -> None:
    """Роль без глобальной области не получает разрешённую область.

    Таблица областей появляется в PHASE 2; до этого отсутствие области
    означает запрет, а не разрешение.
    """
    token = make_test_token("subject-7", [Role.REGIONAL_ANALYST])
    body = client.get(f"{API}/system/whoami", headers=auth(token)).json()

    assert body["roles"] == ["REGIONAL_ANALYST"]
    assert body["scope_resolved"] is False
    assert body["has_global_scope"] is False
    assert body["region_ids"] == []


def test_whoami_does_not_echo_token(client: TestClient) -> None:
    token = make_test_token("subject-8", [Role.HOSPITAL_ANALYST])
    response = client.get(f"{API}/system/whoami", headers=auth(token))
    assert token not in response.text


# --- Долгая операция --------------------------------------------------------


def test_ping_task_registers_operation_before_enqueue(
    client: TestClient,
    operation_service: FakeOperationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Порядок обязателен: сначала запись в PostgreSQL, затем очередь."""
    enqueued: list[uuid.UUID] = []
    monkeypatch.setattr(
        "app.api.v1.system.enqueue_ping",
        lambda operation_id, request_id: enqueued.append(operation_id) or "task-1",  # noqa: ARG005
    )

    response = client.post(f"{API}/system/ping-task", headers=auth("test:admin"))

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == OperationStatus.PENDING
    operation_id = uuid.UUID(body["operation_id"])
    assert operation_id in operation_service.records
    assert enqueued == [operation_id]


def test_ping_task_requires_authentication(client: TestClient) -> None:
    assert client.post(f"{API}/system/ping-task").status_code == 401


def test_broker_failure_marks_operation_failed(
    client: TestClient,
    operation_service: FakeOperationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отказ очереди не приводит к молчаливой потере операции.

    Запись остаётся видимой и переводится в FAILED с понятной причиной.
    """

    def failing_enqueue(operation_id: uuid.UUID, request_id: str | None) -> str:  # noqa: ARG001
        raise ConnectionError("broker unreachable at redis:6379")

    monkeypatch.setattr("app.api.v1.system.enqueue_ping", failing_enqueue)

    response = client.post(f"{API}/system/ping-task", headers=auth("test:admin"))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert "redis:6379" not in response.text

    stored = list(operation_service.records.values())
    assert len(stored) == 1
    assert stored[0].status == OperationStatus.FAILED
    assert stored[0].error_summary == "Очередь задач недоступна"


def test_operation_state_is_readable(
    client: TestClient, operation_service: FakeOperationService
) -> None:
    operation_id = operation_service.register(
        operation_type="system.ping", request_id=None
    )
    operation_service.mark_running(operation_id)
    operation_service.mark_completed(operation_id, result={"pong": True})

    response = client.get(
        f"{API}/system/operations/{operation_id}", headers=auth("test:admin")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == OperationStatus.COMPLETED
    assert body["result"] == {"pong": True}


def test_unknown_operation_returns_404(client: TestClient) -> None:
    response = client.get(
        f"{API}/system/operations/{uuid.uuid4()}", headers=auth("test:admin")
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
