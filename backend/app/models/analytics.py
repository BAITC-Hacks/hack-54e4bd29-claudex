"""Версионированные результаты прогнозов и метаданные сценариев.

Phase 5A сохраняет только краткосрочный глобальный прогноз числа
направлений. Сценарии остаются контрактом хранения до отдельной фазы.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import DataScopeType, ForecastStatus, ScenarioStatus, ScenarioType


class Forecast(Base):
    """Результат прогноза с обязательными сведениями о качестве.

    Прогноз без версии модели, ошибки и периода входных данных
    неинтерпретируем и не отображается (ML_ARCHITECTURE.md, раздел 10).
    """

    __tablename__ = "forecasts"
    __table_args__ = (
        Index("ix_forecasts_hospital_id_generated_at", "hospital_id", "generated_at"),
        Index(
            "ix_forecasts_hospital_id_target_status", "hospital_id", "target", "status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="RESTRICT"),
        nullable=True,
    )
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    scope_type: Mapped[DataScopeType] = mapped_column(
        String(16), nullable=False, default=DataScopeType.HOSPITAL
    )

    # Целевая переменная не зафиксирована архитектурно: она выбирается
    # после Data Audit и хранится как значение, а не как отдельная таблица.
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon_days: Mapped[int] = mapped_column(nullable=False)

    predicted_value: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    lower_bound: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    upper_bound: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)

    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metric_value: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    baseline_metric_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    baseline_metric_value: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )

    input_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    input_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    status: Mapped[ForecastStatus] = mapped_column(
        String(16), nullable=False, default=ForecastStatus.PENDING
    )
    # Причина, по которой прогноз признан непригодным. Прогноз
    # не удаляется: он сохраняется с признаком и объяснением.
    invalidity_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    selected_model: Mapped[str] = mapped_column(
        String(64), nullable=False, default="legacy"
    )
    baseline_model: Mapped[str] = mapped_column(
        String(64), nullable=False, default="legacy"
    )
    feature_schema_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="legacy_v0"
    )
    dataset_watermark: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    validation_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    baseline_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    validation_folds: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    forecast_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    forecast_end: Mapped[date | None] = mapped_column(Date, nullable=True)


class Scenario(Base):
    """Заданный управленческий сценарий.

    Хранит постановку и допущения. Математика расчёта появляется
    в PHASE 7; допущения сохраняются вместе с результатом, потому что
    позже они невоспроизводимы (BUSINESS_LOGIC.md, раздел 7.2).
    """

    __tablename__ = "scenarios"
    __table_args__ = (
        Index("ix_scenarios_hospital_id_created_at", "hospital_id", "created_at"),
        Index("ix_scenarios_created_by_created_at", "created_by", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="SET NULL"), nullable=True
    )

    scenario_type: Mapped[ScenarioType] = mapped_column(String(32), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    assumptions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[ScenarioStatus] = mapped_column(
        String(16), nullable=False, default=ScenarioStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
