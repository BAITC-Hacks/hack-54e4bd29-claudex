"""Сигнал — центральная сущность продукта, и его объяснение."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow
from app.models.enums import (
    DataScopeType,
    ExplanationGenerator,
    SignalClosureDisposition,
    SignalSeverity,
    SignalSourceType,
    SignalStatus,
    SignalType,
)


class Signal(Base):
    """Зафиксированное наблюдение, требующее внимания человека."""

    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'GLOBAL' AND hospital_id IS NULL AND region_id IS NULL) OR "
            "(scope_type = 'REGION' AND hospital_id IS NULL "
            "AND region_id IS NOT NULL) OR "
            "(scope_type = 'HOSPITAL' AND hospital_id IS NOT NULL AND region_id IS NULL)",
            name="scope_target",
        ),
        UniqueConstraint("dedup_key", name="uq_signals_dedup_key"),
        # Лента предупреждений: фильтр по статусу и важности, сортировка
        # по времени обнаружения.
        Index(
            "ix_signals_status_severity_detected_at", "status", "severity", "detected_at"
        ),
        # Сигналы конкретной организации.
        Index("ix_signals_hospital_id_detected_at", "hospital_id", "detected_at"),
        Index("ix_signals_hospital_id_status", "hospital_id", "status"),
        # «Мои сигналы».
        Index("ix_signals_assigned_user_id_status", "assigned_user_id", "status"),
        Index("ix_signals_type", "type"),
        Index("ix_signals_incident_id", "incident_id"),
        Index(
            "ix_signals_scope_status_detected_at",
            "scope_type",
            "region_id",
            "hospital_id",
            "status",
            "detected_at",
        ),
        # Версия начинается с единицы и только растёт: она защищает
        # от потерянного обновления.
        CheckConstraint("version >= 1", name="ck_signals_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scope_type: Mapped[DataScopeType] = mapped_column(
        String(16), nullable=False, default=DataScopeType.HOSPITAL
    )
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=True
    )
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="RESTRICT"),
        nullable=True,
    )

    type: Mapped[SignalType] = mapped_column(String(32), nullable=False)
    severity: Mapped[SignalSeverity] = mapped_column(String(16), nullable=False)
    status: Mapped[SignalStatus] = mapped_column(
        String(16), nullable=False, default=SignalStatus.NEW
    )
    source_type: Mapped[SignalSourceType] = mapped_column(String(16), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    evaluation_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    evaluation_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_value: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    baseline_value: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    delta_absolute: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)
    delta_percent: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)

    rule_code: Mapped[str] = mapped_column(String(96), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    data_watermark: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    data_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    forecast_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("forecasts.id", ondelete="SET NULL"), nullable=True
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Оптимистическая блокировка. Обновление выполняется условием
    # WHERE id = ? AND version = ?; расхождение версии даёт конфликт,
    # а не молчаливую перезапись чужого изменения.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Причина закрытия. Закрытие — управленческий факт, он должен быть
    # объясним (BUSINESS_LOGIC.md, BR-04).
    closed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closure_disposition: Mapped[SignalClosureDisposition | None] = mapped_column(
        String(16), nullable=True
    )

    hospital: Mapped[object | None] = relationship(
        "Hospital", lazy="joined", viewonly=True
    )
    region: Mapped[object | None] = relationship("Region", lazy="joined", viewonly=True)
    explanation: Mapped[SignalExplanation | None] = relationship(
        back_populates="signal", lazy="selectin", cascade="all, delete-orphan"
    )


class SignalExplanation(Base):
    """Объяснение сигнала со сведениями о происхождении.

    Объяснение строится детерминированным кодом по данным: правилами,
    статистикой или разложением вклада признаков модели. Свободный текст
    языковой модели здесь не хранится — происхождение каждого утверждения
    должно быть восстановимо (BUSINESS_LOGIC.md, раздел 5).
    """

    __tablename__ = "signal_explanations"

    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="CASCADE"),
        primary_key=True,
    )

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Факторы в структурированном виде: код показателя, направление,
    # величина изменения, период сравнения.
    factors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    caveats: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # --- Происхождение ---
    generator: Mapped[ExplanationGenerator] = mapped_column(String(32), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    input_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    signal: Mapped[Signal] = relationship(back_populates="explanation", lazy="raise")
