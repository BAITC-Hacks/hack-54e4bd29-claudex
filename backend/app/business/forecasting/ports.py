"""Ports owned by the forecasting business module."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.business.forecasting.contracts import (
    DailyReferralCount,
    ForecastEngineResult,
    OrganizationForecastInput,
    OrganizationForecastRequest,
    ReferralDatasetWatermark,
)
from app.models.analytics import Forecast
from app.models.forecast_point import ForecastPoint
from app.models.model_version import ModelVersion
from app.models.signal import Signal


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


class OrganizationModelEngine(Protocol):
    def admission(
        self, model: ModelVersion, history: OrganizationForecastInput
    ) -> dict[str, object]: ...
    def predict(
        self, model: ModelVersion, history: OrganizationForecastInput
    ) -> ForecastEngineResult: ...


class OrganizationForecastTransaction(Protocol):
    def terminal_result(self) -> dict[str, object] | None: ...
    def registered_model(self, version: str) -> ModelVersion | None: ...
    def locked_input(
        self, request: OrganizationForecastRequest
    ) -> OrganizationForecastInput | None: ...
    def recheck(self, request: OrganizationForecastRequest) -> bool: ...
    def finish(
        self,
        result: dict[str, object],
        *,
        forecast: Forecast | None = None,
        points: tuple[ForecastPoint, ...] = (),
        signal: Signal | None = None,
    ) -> dict[str, object]: ...


class OrganizationForecastRepository(Protocol):
    def transaction(
        self, operation_id: UUID
    ) -> AbstractContextManager[OrganizationForecastTransaction]: ...
