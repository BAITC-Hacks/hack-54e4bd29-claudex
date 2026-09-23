"""Ports required by the descriptive analytics business service."""

from __future__ import annotations

import uuid
from typing import Protocol

from app.business.analytics.contracts import AnalyticsFilter
from app.shared.analytics_data import (
    ImportSummary,
    ImportWatermark,
    QueryScope,
    RawBreakdownCell,
    RawDatasetCoverage,
    RawObservedWaiting,
    RawOrganization,
    RawOverview,
    RawTimeSeriesPoint,
    RawTreatedSnapshot,
    RawWaitingSummary,
)
from app.shared.delivery import DeliveryReadiness

__all__ = [
    "AnalyticsCache",
    "AnalyticsMetadataRepository",
    "AnalyticsRepository",
    "ImportSummary",
    "ImportWatermark",
    "QueryScope",
    "RawBreakdownCell",
    "RawDatasetCoverage",
    "RawObservedWaiting",
    "RawOrganization",
    "RawOverview",
    "RawTimeSeriesPoint",
    "RawTreatedSnapshot",
    "RawWaitingSummary",
]


class AnalyticsRepository(Protocol):
    def overview(self, filters: AnalyticsFilter, scope: QueryScope) -> RawOverview: ...

    def referral_timeseries(
        self, filters: AnalyticsFilter, scope: QueryScope
    ) -> tuple[RawTimeSeriesPoint, ...]: ...

    def refusal_timeseries(
        self, filters: AnalyticsFilter, scope: QueryScope
    ) -> tuple[RawTimeSeriesPoint, ...]: ...

    def waiting_summary(
        self, filters: AnalyticsFilter, scope: QueryScope
    ) -> RawWaitingSummary: ...

    def observed_waiting(
        self, filters: AnalyticsFilter, scope: QueryScope
    ) -> RawObservedWaiting: ...

    def organizations(
        self,
        filters: AnalyticsFilter,
        scope: QueryScope,
        *,
        limit: int,
        offset: int,
    ) -> tuple[tuple[RawOrganization, ...], int]: ...

    def organization_detail(
        self,
        identity_key: str,
        filters: AnalyticsFilter,
        scope: QueryScope,
    ) -> tuple[RawOrganization, RawTreatedSnapshot | None] | None: ...

    def dataset_coverage(self, scope: QueryScope) -> tuple[RawDatasetCoverage, ...]: ...

    def refusal_breakdown(
        self,
        filters: AnalyticsFilter,
        scope: QueryScope,
        *,
        dimension: str,
    ) -> tuple[RawBreakdownCell, ...]: ...


class AnalyticsMetadataRepository(Protocol):
    def delivery_readiness(self, dataset_type: str) -> DeliveryReadiness: ...

    def hospital_ids_for_regions(
        self, region_ids: tuple[uuid.UUID, ...]
    ) -> tuple[uuid.UUID, ...]: ...

    def latest_completed_imports(self) -> ImportWatermark: ...

    def latest_import_summaries(self) -> tuple[ImportSummary, ...]: ...

    def hospital_name(self, hospital_id: uuid.UUID) -> str | None: ...


class AnalyticsCache(Protocol):
    def get_overview(self, key: str) -> RawOverview | None: ...

    def set_overview(self, key: str, value: RawOverview, ttl_seconds: int) -> None: ...
