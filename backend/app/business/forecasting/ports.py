"""Ports owned by the forecasting business module."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.business.forecasting.contracts import (
    DailyReferralCount,
    ForecastEngineResult,
    ReferralDatasetWatermark,
)


class ReferralHistoryRepository(Protocol):
    def daily_global(self) -> tuple[DailyReferralCount, ...]: ...


class ForecastMetadataRepository(Protocol):
    def referral_watermark(self) -> ReferralDatasetWatermark: ...


class ForecastEnginePort(Protocol):
    def train(
        self,
        history: tuple[DailyReferralCount, ...],
        watermark: ReferralDatasetWatermark,
        *,
        generated_at: datetime,
    ) -> ForecastEngineResult: ...
