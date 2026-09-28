"""Подключение к Redis.

Три назначения на разных логических базах (ADR-0003): кэш, брокер задач,
счётчики ограничения частоты. Разделение баз позволяет разные политики
вытеснения: кэш вытеснять можно, очередь задач — нельзя.

Redis не является источником истины для состояния бизнес-операций:
оно живёт в PostgreSQL (ADR-0010).
"""

from __future__ import annotations

from functools import lru_cache

from redis import Redis

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_cache_client() -> Redis:
    """Клиент для кэша. Отказ кэша не должен ломать обработку запроса."""
    settings = get_settings()
    return Redis.from_url(
        settings.redis_cache_url,
        decode_responses=True,
        socket_timeout=settings.redis_socket_timeout_s,
        socket_connect_timeout=settings.redis_socket_timeout_s,
        health_check_interval=30,
    )


def check_connection(timeout_s: float) -> None:
    """Проверка доступности для readiness. Бросает исключение при отказе."""
    settings = get_settings()
    client = Redis.from_url(
        settings.redis_cache_url,
        decode_responses=True,
        socket_timeout=timeout_s,
        socket_connect_timeout=timeout_s,
    )
    try:
        client.ping()
    finally:
        client.close()


def close_clients() -> None:
    if get_cache_client.cache_info().currsize:
        get_cache_client().close()
