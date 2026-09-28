"""Versioned provenance for registered forecasting candidates."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import ModelVersionStatus


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    target: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    mlflow_run_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    feature_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    training_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    training_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    training_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    baseline_metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    validation_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dataset_watermark: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    selection_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ModelVersionStatus] = mapped_column(
        String(16), nullable=False, default=ModelVersionStatus.SELECTED
    )
