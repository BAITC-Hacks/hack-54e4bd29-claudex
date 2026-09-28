"""Immutable date points belonging to a versioned forecast run."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ForecastPoint(Base):
    __tablename__ = "forecast_points"
    __table_args__ = (
        UniqueConstraint(
            "forecast_id", "forecast_date", name="uq_forecast_points_forecast_date"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    forecast_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("forecasts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_value: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    baseline_value: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
