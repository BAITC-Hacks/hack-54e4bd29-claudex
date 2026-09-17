"""Ports consumed by Signal Engine orchestration."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from app.shared.signal_engine import (
    ForecastEvidence,
    FreshnessEvidence,
    QualityMeasurement,
    TimeSeriesEvidence,
)


class SignalInputRepository(Protocol):
    def freshness_evidence(self) -> tuple[FreshnessEvidence, ...]: ...

    def quality_measurements(self) -> tuple[QualityMeasurement, ...]: ...

    def daily_evidence(
        self,
        dataset_type: str,
        *,
        before: date,
        source_is_current: bool,
        limit_days: int,
    ) -> TimeSeriesEvidence: ...

    def latest_forecast(self, *, now: datetime) -> ForecastEvidence | None: ...
