"""Подключение к ClickHouse.

Аналитическое хранилище: неизменяемые наблюдения во времени (ADR-0002).
Клиент ограничен по времени выполнения и по числу возвращаемых строк —
неограниченная выборка из исторического слоя недопустима.
"""

from __future__ import annotations

from functools import lru_cache

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    settings = get_settings()
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_db,
        secure=settings.clickhouse_secure,
        connect_timeout=settings.clickhouse_connect_timeout_s,
        send_receive_timeout=settings.clickhouse_max_execution_time_s,
        client_name=settings.app_name,
        settings={
            "max_execution_time": settings.clickhouse_max_execution_time_s,
        },
    )


def check_connection(timeout_s: float) -> None:
    """Проверка доступности для readiness. Бросает исключение при отказе.

    Создаётся отдельный короткоживущий клиент: проверка готовности не должна
    зависеть от состояния основного пула и не должна его занимать.
    """
    settings = get_settings()
    client = clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_db,
        secure=settings.clickhouse_secure,
        connect_timeout=max(1, int(timeout_s)),
        send_receive_timeout=max(1, int(timeout_s)),
        client_name=f"{settings.app_name}-readiness",
    )
    try:
        client.command("SELECT 1")
    finally:
        client.close()


def close_client() -> None:
    if get_client.cache_info().currsize:
        get_client().close()
