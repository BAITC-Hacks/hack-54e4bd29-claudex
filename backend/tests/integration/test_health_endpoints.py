"""Эндпоинты здоровья и готовности."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import health as health_module

API = "/api/v1"


def test_health_returns_200_without_touching_dependencies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Liveness не должен падать из-за недоступной базы.

    Оркестратор перезапускает контейнер по этой проверке: зависимость
    от внешних сервисов превратила бы сбой базы в цикл перезапусков.
    """

    def explode(_timeout: float) -> None:
        raise AssertionError("health не должен проверять зависимости")

    monkeypatch.setattr(
        health_module,
        "DEPENDENCY_CHECKS",
        {"postgres": explode, "clickhouse": explode, "redis": explode},
    )

    response = client.get(f"{API}/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "medsignal"
    assert body["environment"] == "local"


def test_ready_returns_200_when_required_dependencies_are_up(
    client: TestClient,
    all_dependencies_up: None,  # noqa: ARG001 - фикстура применяется по факту
) -> None:
    response = client.get(f"{API}/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    names = {item["name"] for item in body["dependencies"]}
    assert {"postgres", "clickhouse", "redis"} <= names
    assert all(item["status"] == "up" for item in body["dependencies"])


def test_ready_returns_503_when_required_dependency_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(_timeout: float) -> None:
        raise ConnectionError("недоступно")

    monkeypatch.setattr(
        health_module,
        "DEPENDENCY_CHECKS",
        {
            "postgres": failing,
            "clickhouse": lambda _t: None,
            "redis": lambda _t: None,
            "object_storage": lambda _t: None,
        },
    )

    response = client.get(f"{API}/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    postgres = next(d for d in body["dependencies"] if d["name"] == "postgres")
    assert postgres["status"] == "down"
    assert postgres["required"] is True


def test_optional_dependency_failure_does_not_block_readiness(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Готовность определяется только обязательными зависимостями.

    Иначе она начинает мерцать из-за второстепенного сервиса.
    """

    def failing(_timeout: float) -> None:
        raise ConnectionError("недоступно")

    monkeypatch.setattr(
        health_module,
        "DEPENDENCY_CHECKS",
        {
            "postgres": lambda _t: None,
            "clickhouse": lambda _t: None,
            "redis": lambda _t: None,
            "object_storage": failing,
        },
    )

    response = client.get(f"{API}/ready")

    assert response.status_code == 200
    storage = next(
        d for d in response.json()["dependencies"] if d["name"] == "object_storage"
    )
    assert storage["status"] == "down"
    assert storage["required"] is False


def test_readiness_reason_does_not_leak_internal_details(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Причина отказа не раскрывает адреса и имена внутренних сервисов."""

    def failing(_timeout: float) -> None:
        raise ConnectionError(
            "could not connect to server at 10.0.7.31 port 5432 database medsignal"
        )

    monkeypatch.setattr(health_module, "DEPENDENCY_CHECKS", {"postgres": failing})

    body = client.get(f"{API}/ready").json()
    serialized = str(body)
    assert "10.0.7.31" not in serialized
    assert "5432" not in serialized


def test_metrics_are_not_exposed_under_api_prefix(client: TestClient) -> None:
    """Метрики не должны быть доступны через публичный префикс API."""
    assert client.get(f"{API}/metrics").status_code == 404
