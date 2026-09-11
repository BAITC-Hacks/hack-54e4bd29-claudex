"""Идентификатор запроса.

`request_id` связывает ответ, записи журнала и фоновую задачу.
Без него разбор инцидента невозможен (SECURITY.md, раздел 12).
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter
from app.core.request_context import REQUEST_ID_HEADER

API = "/api/v1"


def test_response_contains_request_id_header(client: TestClient) -> None:
    response = client.get(f"{API}/health")
    assert response.headers.get(REQUEST_ID_HEADER)


def test_client_supplied_request_id_is_preserved(client: TestClient) -> None:
    """Идентификатор, заданный клиентом, позволяет связать его журнал с нашим."""
    supplied = "a1b2c3d4e5f6a7b8"
    response = client.get(f"{API}/health", headers={REQUEST_ID_HEADER: supplied})
    assert response.headers[REQUEST_ID_HEADER] == supplied


@pytest.mark.parametrize(
    "malicious",
    [
        "short",
        "value with spaces",
        "id;charset=evil",
        "<script>alert(1)</script>",
        "x" * 200,
    ],
)
def test_unsafe_request_id_is_replaced(client: TestClient, malicious: str) -> None:
    """Внешнее значение попадает в журнал и в заголовок ответа.

    Поэтому принимается только безопасная форма: непригодное значение
    заменяется собственным, а запрос обслуживается.
    """
    response = client.get(f"{API}/health", headers={REQUEST_ID_HEADER: malicious})

    returned = response.headers[REQUEST_ID_HEADER]
    assert returned != malicious
    assert returned.isalnum()


def test_each_request_gets_distinct_identifier(client: TestClient) -> None:
    first = client.get(f"{API}/health").headers[REQUEST_ID_HEADER]
    second = client.get(f"{API}/health").headers[REQUEST_ID_HEADER]
    assert first != second


def test_request_id_appears_in_access_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    supplied = "logcorrelation01"
    with caplog.at_level(logging.INFO, logger="medsignal.access"):
        client.get(f"{API}/health", headers={REQUEST_ID_HEADER: supplied})

    formatter = JsonFormatter(service="medsignal", environment="local")
    rendered = [json.loads(formatter.format(record)) for record in caplog.records]
    assert any(entry.get("message") == "Запрос обработан" for entry in rendered)


def test_access_log_does_not_contain_authorization_header(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Заголовки запроса не логируются: они могут содержать токен."""
    secret = "Bearer super-secret-token-value"
    with caplog.at_level(logging.INFO):
        client.get(f"{API}/health", headers={"Authorization": secret})

    formatter = JsonFormatter(service="medsignal", environment="local")
    rendered = " ".join(formatter.format(record) for record in caplog.records)
    assert "super-secret-token-value" not in rendered
