"""Системные таблицы PHASE 1.

`system_operations` реализует общий жизненный цикл долгих операций
из ADR-0010: PENDING → RUNNING → COMPLETED | FAILED.

Это единственная таблица, создаваемая в PHASE 1. Доменные таблицы —
регионы, организации, сигналы — появляются в PHASE 2.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class OperationStatus(StrEnum):
    """Статусы долгой операции (ADR-0010)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in (OperationStatus.COMPLETED, OperationStatus.FAILED)


class SystemOperation(Base):
    """Состояние долгой операции.

    Запись создаётся до постановки задачи в очередь и обновляется воркером
    транзакционно. Потерянная задача остаётся видимой в статусе PENDING.
    """

    __tablename__ = "system_operations"
    __table_args__ = (
        Index("ix_system_operations_status_created_at", "status", "created_at"),
        Index("ix_system_operations_request_id", "request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[OperationStatus] = mapped_column(
        String(16), nullable=False, default=OperationStatus.PENDING
    )

    # Связь с породившим HTTP-запросом и записями журнала.
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Краткая причина отказа для пользователя. Трассировка сюда не попадает:
    # она остаётся в журнале, связанном по request_id (ADR-0010).
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
