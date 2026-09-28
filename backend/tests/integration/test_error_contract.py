"""Единый контракт ошибок.

Клиент всегда получает одну и ту же форму ответа, и она никогда
не содержит трассировку или внутренние имена (API.md, раздел 1.2).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import INTERNAL_ERROR_MESSAGE, ConflictError
from app.core.request_context import REQUEST_ID_HEADER

API = "/api/v1"


def assert_error_shape(payload: dict) -> dict:
    assert set(payload) == {"error"}
    error = payload["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert isinstance(error["code"], str) and error["code"]
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"], dict)
    return error


def test_unknown_route_uses_error_contract(client: TestClient) -> None:
    response = client.get(f"{API}/no-such-route")
    assert response.status_code == 404
    error = assert_error_shape(response.json())
    assert error["code"] == "NOT_FOUND"


def test_error_response_carries_request_id(client: TestClient) -> None:
    """Ошибка должна быть связуема с журналом."""
    response = client.get(f"{API}/no-such-route")
    error = response.json()["error"]
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_validation_error_lists_fields(client: TestClient) -> None:
    # Аутентификация проверяется раньше разбора параметров пути,
    # поэтому для проверки валидации нужен действительный токен.
    response = client.get(
        f"{API}/system/operations/not-a-uuid",
        headers={"Authorization": "Bearer test:admin"},
    )
    assert response.status_code == 422
    error = assert_error_shape(response.json())
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["fields"]


def test_method_not_allowed_uses_error_contract(client: TestClient) -> None:
    response = client.delete(f"{API}/health")
    assert response.status_code == 405
    assert_error_shape(response.json())


def test_domain_error_maps_to_status_code(app: FastAPI, client: TestClient) -> None:
    @app.get("/api/v1/_test/conflict")
    def _conflict() -> None:
        raise ConflictError("Недопустимый переход статуса")

    response = client.get(f"{API}/_test/conflict")

    assert response.status_code == 409
    error = assert_error_shape(response.json())
    assert error["code"] == "CONFLICT"
    assert error["message"] == "Недопустимый переход статуса"


def test_unexpected_exception_does_not_leak_details(
    app: FastAPI, client: TestClient
) -> None:
    """Наружу уходит общее сообщение, подробности остаются в журнале."""
    marker = "секретная-строка-из-трассировки"

    @app.get("/api/v1/_test/boom")
    def _boom() -> None:
        raise RuntimeError(marker)

    response = client.get(f"{API}/_test/boom")

    assert response.status_code == 500
    error = assert_error_shape(response.json())
    assert error["code"] == "INTERNAL_ERROR"
    assert error["message"] == INTERNAL_ERROR_MESSAGE

    body = response.text
    assert marker not in body
    assert "Traceback" not in body
    assert "RuntimeError" not in body
    assert ".py" not in body


@pytest.mark.parametrize("path", ["/system/whoami", "/system/ping-task"])
def test_unauthenticated_requests_use_error_contract(
    client: TestClient, path: str
) -> None:
    response = (
        client.get(f"{API}{path}")
        if path.endswith("whoami")
        else client.post(f"{API}{path}")
    )
    assert response.status_code == 401
    error = assert_error_shape(response.json())
    assert error["code"] == "UNAUTHENTICATED"
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_security_headers_present_on_error_responses(client: TestClient) -> None:
    response = client.get(f"{API}/no-such-route")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
