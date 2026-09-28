"""Concurrency contract for the shared ClickHouse HTTP client."""

from __future__ import annotations

from typing import Any

from app.database import clickhouse


def test_shared_client_disables_server_session(monkeypatch: Any) -> None:
    """A session-bound client rejects concurrent analytics queries."""
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_get_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    clickhouse.get_client.cache_clear()
    monkeypatch.setattr(clickhouse.clickhouse_connect, "get_client", fake_get_client)

    assert clickhouse.get_client() is sentinel
    assert captured["autogenerate_session_id"] is False
    clickhouse.get_client.cache_clear()
