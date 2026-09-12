"""Инцидент — группа связанных сигналов одной ситуации."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow
from app.models.enums import IncidentStatus


class Incident(Base):
    """Ситуация, объединяющая несколько сигналов.

    Группировка на этом этапе выполняется человеком: автоматическая
    кластеризация требует накопленной статистики совместных срабатываний
    и отложена (ADR-0008, раздел «Пересмотр»).
    """

    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_hospital_id_status", "hospital_id", "status"),
        Index("ix_incidents_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[IncidentStatus] = mapped_column(
        String(16), nullable=False, default=IncidentStatus.OPEN
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    signals: Mapped[list[object]] = relationship("Signal", lazy="raise", viewonly=True)
