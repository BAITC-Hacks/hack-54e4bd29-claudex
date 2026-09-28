"""Подключение к PostgreSQL.

Операционное хранилище: состояние, связи, транзакции (ADR-0002).
Движок создаётся один раз на процесс; пул ограничен настройками.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return _build_engine(settings)


def _build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.postgres_dsn,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout=settings.postgres_pool_timeout_s,
        pool_pre_ping=True,  # соединение, разорванное простоем, не доходит до запроса
        future=True,
        echo=False,
        connect_args={
            "connect_timeout": settings.postgres_connect_timeout_s,
            "sslmode": settings.postgres_sslmode,
            # Ограничение времени запроса: ни один запрос не удерживает
            # соединение дольше бюджета (PERFORMANCE, DATABASE.md раздел 6).
            "options": f"-c statement_timeout={settings.postgres_statement_timeout_ms}",
            "application_name": settings.app_name,
        },
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Сессия с транзакцией: фиксация при успехе, откат при ошибке."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection(timeout_s: float) -> None:
    """Проверка доступности для readiness. Бросает исключение при отказе."""
    engine = get_engine()
    with engine.connect() as connection:
        connection.execute(text(f"SET LOCAL statement_timeout = {int(timeout_s * 1000)}"))
        connection.execute(text("SELECT 1"))


def dispose_engine() -> None:
    """Закрыть пул. Вызывается при остановке приложения."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
