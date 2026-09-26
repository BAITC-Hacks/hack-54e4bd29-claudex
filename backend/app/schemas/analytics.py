"""Strict public contracts for descriptive aggregate analytics."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.analytics_contracts import (
    FreshnessStatus,
    Granularity,
    MetricName,
    OrganizationMappingStatus,
)

_RESPONSE = ConfigDict(extra="forbid")


class AnalyticsCellResponse(BaseModel):
    model_config = _RESPONSE

    value: int | float | None
    suppressed: bool


class AnalyticsMetaResponse(BaseModel):
    model_config = _RESPONSE

    date_from: datetime
    date_to: datetime
    granularity: Granularity | None = None
    source: list[str]
    generated_at: datetime
    latest_import_id: str | None
    latest_import_ids: list[str]
    latest_import_completed_at: datetime | None
    limitations: list[str]
    mapping_version: str | None = None
    mapping_publication_available: bool = False


class OverviewData(BaseModel):
    model_config = _RESPONSE

    referrals_total: AnalyticsCellResponse
    waiting_records: AnalyticsCellResponse
    refusals_total: AnalyticsCellResponse
    hospitalized_total: AnalyticsCellResponse
    data_quality_warnings: AnalyticsCellResponse
    represented_organizations: AnalyticsCellResponse
    represented_regions: AnalyticsCellResponse


class OverviewResponse(BaseModel):
    model_config = _RESPONSE

    data: OverviewData
    meta: AnalyticsMetaResponse


class TimeSeriesPointResponse(BaseModel):
    model_config = _RESPONSE

    period: datetime
    period_end: datetime
    value: AnalyticsCellResponse


class TimeSeriesData(BaseModel):
    model_config = _RESPONSE

    metric: MetricName
    points: list[TimeSeriesPointResponse]


class TimeSeriesResponse(BaseModel):
    model_config = _RESPONSE

    data: TimeSeriesData
    meta: AnalyticsMetaResponse


class WaitingSummaryData(BaseModel):
    model_config = _RESPONSE

    snapshot_at: datetime | None = None
    snapshot_semantics_confirmed: bool = False
    waiting_records: AnalyticsCellResponse
    median_days: AnalyticsCellResponse
    p75_days: AnalyticsCellResponse
    p90_days: AnalyticsCellResponse
    oldest_days: AnalyticsCellResponse


class WaitingSummaryResponse(BaseModel):
    model_config = _RESPONSE

    data: WaitingSummaryData
    meta: AnalyticsMetaResponse


class ObservedWaitingData(BaseModel):
    model_config = _RESPONSE

    observed_records: AnalyticsCellResponse
    excluded_chronology_conflicts: AnalyticsCellResponse
    mean_days: AnalyticsCellResponse
    median_days: AnalyticsCellResponse
    p75_days: AnalyticsCellResponse
    p90_days: AnalyticsCellResponse


class ObservedWaitingResponse(BaseModel):
    model_config = _RESPONSE

    data: ObservedWaitingData
    meta: AnalyticsMetaResponse


class OrganizationData(BaseModel):
    model_config = _RESPONSE

    organization_ref: str
    canonical_hospital_id: uuid.UUID | None
    display_name: str | None
    identity_label: str | None
    mapping_status: OrganizationMappingStatus
    source_system: str | None
    region_id: uuid.UUID | None
    referrals_total: AnalyticsCellResponse
    waiting_records: AnalyticsCellResponse
    refusals_total: AnalyticsCellResponse
    observed_waiting_median_days: AnalyticsCellResponse


class OrganizationListData(BaseModel):
    model_config = _RESPONSE

    items: list[OrganizationData]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    has_next: bool


class OrganizationListResponse(BaseModel):
    model_config = _RESPONSE

    data: OrganizationListData
    meta: AnalyticsMetaResponse


class TreatedSnapshotResponse(BaseModel):
    model_config = _RESPONSE

    label: str = "Показатели пролеченных случаев — предоставленный срез"
    snapshot_load_dt: datetime
    discharged_total: int
    discharged_children: int
    treated_budget: int
    treated_paid: int
    discharged_within_day: int
    deaths_total: int
    bed_days: int
    amount_to_pay: float


class OrganizationDetailData(BaseModel):
    model_config = _RESPONSE

    organization: OrganizationData
    treated_snapshot: TreatedSnapshotResponse | None


class OrganizationDetailResponse(BaseModel):
    model_config = _RESPONSE

    data: OrganizationDetailData
    meta: AnalyticsMetaResponse


class DatasetFreshnessResponse(BaseModel):
    model_config = _RESPONSE

    dataset_type: str
    event_period_start: datetime | None
    event_period_end: datetime | None
    source_load_date: datetime | None
    last_successful_import: datetime | None
    status: FreshnessStatus
    explanation: str | None
    confirmed_complete_through: date | None = None
    cadence_known: bool = False
    completeness: str = "UNKNOWN"
    forecast_available: bool = False


class FreshnessResponse(BaseModel):
    model_config = _RESPONSE

    data: list[DatasetFreshnessResponse]
    meta: AnalyticsMetaResponse


class DatasetQualityResponse(BaseModel):
    model_config = _RESPONSE

    dataset_type: str
    status: str
    rows_loaded: int
    warnings_count: int
    rejected_count: int
    issues: list[str]


class QualityResponse(BaseModel):
    model_config = _RESPONSE

    data: list[DatasetQualityResponse]
    meta: AnalyticsMetaResponse


class BreakdownItemResponse(BaseModel):
    model_config = _RESPONSE

    label: str
    count: AnalyticsCellResponse


class BreakdownData(BaseModel):
    model_config = _RESPONSE

    dimension: str
    items: list[BreakdownItemResponse]


class BreakdownResponse(BaseModel):
    model_config = _RESPONSE

    data: BreakdownData
    meta: AnalyticsMetaResponse
