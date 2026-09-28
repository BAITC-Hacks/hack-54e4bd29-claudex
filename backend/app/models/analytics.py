"""Версионированные результаты прогнозов и метаданные сценариев.

Phase 5A сохраняет только краткосрочный глобальный прогноз числа
направлений. Сценарии остаются контрактом хранения до отдельной фазы.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import (
    BaselineFreshnessStatus,
    DataScopeType,
    ForecastStatus,
    ScenarioBaselineType,
    ScenarioStatus,
    ScenarioType,
)


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
        Index(
            "ix_forecasts_scope_target_generated_at",
            "scope_type",
            "target",
            "generated_at",
        ),
        Index("ix_forecasts_model_version_id", "model_version_id"),
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
    """Неизменяемый детерминированный расчётный сценарий Phase 7."""

    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'GLOBAL' AND hospital_id IS NULL AND region_id IS NULL) OR "
            "(scope_type = 'REGION' AND hospital_id IS NULL "
            "AND region_id IS NOT NULL) OR "
            "(scope_type = 'HOSPITAL' AND hospital_id IS NOT NULL AND region_id IS NULL)",
            name="scope_target",
        ),
        CheckConstraint("baseline_value > 0", name="baseline_positive"),
        UniqueConstraint(
            "created_by", "client_request_id", name="uq_scenarios_actor_request"
        ),
        Index("ix_scenarios_hospital_id_created_at", "hospital_id", "created_at"),
        Index(
            "ix_scenarios_scope_created_at",
            "scope_type",
            "region_id",
            "hospital_id",
            "created_at",
        ),
        Index("ix_scenarios_source_signal_id", "source_signal_id"),
        Index("ix_scenarios_source_incident_id", "source_incident_id"),
        Index("ix_scenarios_created_by_created_at", "created_by", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scope_type: Mapped[DataScopeType] = mapped_column(String(16), nullable=False)
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=True
    )
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="SET NULL"), nullable=True
    )
    source_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
    )

    scenario_type: Mapped[ScenarioType] = mapped_column(String(32), nullable=False)
    baseline_type: Mapped[ScenarioBaselineType] = mapped_column(
        String(16), nullable=False
    )
    baseline_value: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    baseline_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    assumption_value: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    calculated_value: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    delta_absolute: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    delta_percent: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    data_watermark: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    forecast_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("forecasts.id", ondelete="RESTRICT"), nullable=True
    )
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    forecast_status: Mapped[ForecastStatus | None] = mapped_column(
        String(16), nullable=True
    )
    baseline_freshness_status: Mapped[BaselineFreshnessStatus] = mapped_column(
        String(16), nullable=False
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    limitations_snapshot: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)
    limitations_version: Mapped[str] = mapped_column(String(64), nullable=False)
    client_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    status: Mapped[ScenarioStatus] = mapped_column(
        String(16), nullable=False, default=ScenarioStatus.COMPLETED
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
