"""Действие человека.

Action фиксирует решение уполномоченного сотрудника. Система никогда
не создаёт Action от своего имени: записи, порождённые автоматикой,
имеют иной тип и не выдаются за решение человека
(BUSINESS_LOGIC.md, раздел 8).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import ActionType


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (
        Index("ix_actions_signal_id_created_at", "signal_id", "created_at"),
        Index("ix_actions_incident_id_created_at", "incident_id", "created_at"),
        # Действие обязано относиться хотя бы к одному объекту,
        # иначе его невозможно интерпретировать.
        CheckConstraint(
            "signal_id IS NOT NULL OR incident_id IS NOT NULL",
            name="ck_actions_target_present",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), nullable=True
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True
    )
    # Автор действия обязателен: действие без автора не является
    # решением человека.
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action_type: Mapped[ActionType] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
