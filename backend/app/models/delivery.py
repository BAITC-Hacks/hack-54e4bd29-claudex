"""Persisted reviewed manifest, reservation and expected file parts."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    delivery_id: Mapped[str] = mapped_column(String(128), unique=True)
    dataset_type: Mapped[str] = mapped_column(String(64))
    source_system: Mapped[str] = mapped_column(String(64))
    contract_version: Mapped[str] = mapped_column(String(128))
    manifest: Mapped[dict] = mapped_column(JSONB)
    manifest_digest: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    snapshot_date: Mapped[date | None] = mapped_column(Date)
    confirmed_complete_through: Mapped[date | None] = mapped_column(Date)
    cadence_days: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(16), default="APPROVED")
    reason: Mapped[str | None] = mapped_column(String(64))
    evidence_ref: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str] = mapped_column(String(256))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeliveryPart(Base):
    __tablename__ = "delivery_parts"
    __table_args__ = (
        UniqueConstraint(
            "delivery_id", "file_hash", name="uq_delivery_parts_delivery_hash"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deliveries.id"))
    file_hash: Mapped[str] = mapped_column(String(64))
