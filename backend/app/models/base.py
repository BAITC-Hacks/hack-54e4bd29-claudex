"""Базовый класс моделей SQLAlchemy.

Модели описывают таблицы и не содержат логики (ARCHITECTURE.md, раздел 3.3).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Явные шаблоны имён ограничений: без них Alembic генерирует миграции
# с автоименованными ограничениями, которые невозможно откатить.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    """Текущий момент в UTC. Хранение времени — всегда в UTC."""
    return datetime.now(tz=UTC)
