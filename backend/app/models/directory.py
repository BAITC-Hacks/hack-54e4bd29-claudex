"""Справочники: регионы и медицинские организации.

Медицинских полей здесь нет намеренно. Профиль организации, мощность
и коечный фонд появятся только после того, как Data Audit подтвердит
их наличие в реальных выгрузках (ADR-0007).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class Region(Base):
    """Административная единица, объединяющая медицинские организации."""

    __tablename__ = "regions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Внешний код региона. Уникален: по нему выполняется сопоставление
    # со справочниками источников.
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    hospitals: Mapped[list[Hospital]] = relationship(
        back_populates="region", lazy="raise"
    )


class Hospital(Base):
    """Медицинская организация."""

    __tablename__ = "hospitals"
    __table_args__ = (
        # Список организаций региона — основной сценарий выборки.
        Index("ix_hospitals_region_id", "region_id"),
        Index("ix_hospitals_region_id_is_active", "region_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    region: Mapped[Region] = relationship(back_populates="hospitals", lazy="joined")
