"""Aggregate-only Situation Center API."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal, TypeVar

from fastapi import APIRouter, Query

from app.api.deps import AnalyticsServiceDep, CurrentUser
from app.business.analytics.contracts import (
    AnalyticsCell,
    AnalyticsFilter,
    AnalyticsMetadata,
    Granularity,
    OrganizationIdentity,
    OrganizationIdentitySpace,
    OrganizationMappingStatus,
    OrganizationSummary,
    TimeSeriesResult,
)
from app.core.exceptions import ValidationError
from app.schemas.analytics import (
    AnalyticsCellResponse,
    AnalyticsMetaResponse,
    BreakdownData,
    BreakdownItemResponse,
    BreakdownResponse,
    DatasetFreshnessResponse,
    DatasetQualityResponse,
    FreshnessResponse,
    ObservedWaitingData,
    ObservedWaitingResponse,
    OrganizationData,
    OrganizationDetailData,
    OrganizationDetailResponse,
    OrganizationListData,
    OrganizationListResponse,
    OverviewData,
    OverviewResponse,
    QualityResponse,
    TimeSeriesData,
    TimeSeriesPointResponse,
    TimeSeriesResponse,
    TreatedSnapshotResponse,
    WaitingSummaryData,
    WaitingSummaryResponse,
)
from app.schemas.common import ERROR_RESPONSES
from app.shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

router = APIRouter(prefix="/analytics", tags=["analytics"], responses=ERROR_RESPONSES)

DEFAULT_DATE_FROM = datetime(2025, 1, 1, tzinfo=UTC)
DEFAULT_DATE_TO = datetime(2025, 3, 31, 23, 59, 59, 999000, tzinfo=UTC)
BreakdownDimension = Literal[
    "finance_source", "icd_group", "resident", "insured", "benefit_category"
]
CellT = TypeVar("CellT", int, float)


def _cell(value: AnalyticsCell[CellT]) -> AnalyticsCellResponse:
    return AnalyticsCellResponse(value=value.value, suppressed=value.suppressed)


def _meta(metadata: AnalyticsMetadata) -> AnalyticsMetaResponse:
    return AnalyticsMetaResponse(
        date_from=metadata.date_from,
        date_to=metadata.date_to,
        granularity=metadata.granularity,
        source=list(metadata.sources),
        generated_at=metadata.generated_at,
        latest_import_id=(
            metadata.latest_import_ids[0] if metadata.latest_import_ids else None
        ),
        latest_import_ids=list(metadata.latest_import_ids),
        latest_import_completed_at=metadata.completed_import_watermark,
        limitations=list(metadata.limitations),
    )


def _identity(raw: str) -> OrganizationIdentity:
    try:
        namespace, _, _value = raw.partition(":")
        if namespace == "canonical":
            return OrganizationIdentity(
                raw,
                OrganizationIdentitySpace.CANONICAL,
                OrganizationMappingStatus.MAPPED,
            )
        if namespace == "source":
            return OrganizationIdentity(
                raw,
                OrganizationIdentitySpace.SOURCE,
                OrganizationMappingStatus.UNMAPPED,
            )
    except ValueError as exc:
        raise ValidationError("Некорректная ссылка на организацию") from exc
    raise ValidationError("Некорректная ссылка на организацию")


def _filters(
    date_from: datetime,
    date_to: datetime,
    granularity: Granularity,
    region: tuple[uuid.UUID, ...],
    organization: tuple[str, ...],
    profile: str | None,
) -> AnalyticsFilter:
    return AnalyticsFilter(
        date_from=date_from,
        date_to=date_to,
        granularity=granularity,
        region_ids=region,
        organization_ids=tuple(_identity(item) for item in organization),
        profile=profile,
    )


DateFrom = Annotated[datetime, Query()]
DateTo = Annotated[datetime, Query()]
Regions = Annotated[tuple[uuid.UUID, ...], Query(alias="region")]
Organizations = Annotated[tuple[str, ...], Query(alias="organization")]
Profile = Annotated[str | None, Query(min_length=1, max_length=200)]


def _organization(summary: OrganizationSummary) -> OrganizationData:
    return OrganizationData(
        organization_ref=summary.identity.key,
        canonical_hospital_id=summary.canonical_hospital_id,
        display_name=summary.organization_name,
        identity_label=summary.identity_label,
        mapping_status=summary.identity.mapping_status,
        source_system=summary.source_system,
        region_id=summary.region_id,
        referrals_total=_cell(summary.referrals_total),
        waiting_records=_cell(summary.waiting_records),
        refusals_total=_cell(summary.refusals_total),
        observed_waiting_median_days=_cell(summary.observed_waiting_median_days),
    )


@router.get("/overview", response_model=OverviewResponse)
def overview(
    context: CurrentUser,
    service: AnalyticsServiceDep,
    date_from: DateFrom = DEFAULT_DATE_FROM,
    date_to: DateTo = DEFAULT_DATE_TO,
    region: Regions = (),
    organization: Organizations = (),
    profile: Profile = None,
) -> OverviewResponse:
    result = service.overview(
        context,
        _filters(date_from, date_to, Granularity.DAY, region, organization, profile),
    )
    return OverviewResponse(
        data=OverviewData(
            referrals_total=_cell(result.referrals_total),
            waiting_records=_cell(result.waiting_records),
            refusals_total=_cell(result.refusals_total),
            hospitalized_total=_cell(result.hospitalized_total),
            data_quality_warnings=_cell(result.unknown_records),
            represented_organizations=_cell(result.represented_organizations),
            represented_regions=_cell(result.represented_regions),
        ),
        meta=_meta(result.metadata),
    )


def _timeseries_response(result: TimeSeriesResult) -> TimeSeriesResponse:
    return TimeSeriesResponse(
        data=TimeSeriesData(
            metric=result.metric,
            points=[
                TimeSeriesPointResponse(
                    period=item.period_start,
                    period_end=item.period_end,
                    value=_cell(item.value),
                )
                for item in result.points
            ],
        ),
        meta=_meta(result.metadata),
    )


@router.get("/referrals/timeseries", response_model=TimeSeriesResponse)
def referral_timeseries(
    context: CurrentUser,
    service: AnalyticsServiceDep,
    date_from: DateFrom = DEFAULT_DATE_FROM,
    date_to: DateTo = DEFAULT_DATE_TO,
    granularity: Granularity = Granularity.DAY,
    region: Regions = (),
    organization: Organizations = (),
    profile: Profile = None,
) -> TimeSeriesResponse:
    return _timeseries_response(
        service.referral_timeseries(
            context,
            _filters(date_from, date_to, granularity, region, organization, profile),
        )
    )


@router.get("/refusals/timeseries", response_model=TimeSeriesResponse)
def refusal_timeseries(
    context: CurrentUser,
    service: AnalyticsServiceDep,
    date_from: DateFrom = DEFAULT_DATE_FROM,
    date_to: DateTo = DEFAULT_DATE_TO,
    granularity: Granularity = Granularity.DAY,
    region: Regions = (),
    organization: Organizations = (),
) -> TimeSeriesResponse:
    return _timeseries_response(
        service.refusal_timeseries(
            context,
            _filters(date_from, date_to, granularity, region, organization, None),
        )
    )


@router.get("/waiting/summary", response_model=WaitingSummaryResponse)
def waiting_summary(
    context: CurrentUser,
    service: AnalyticsServiceDep,
    date_from: DateFrom = DEFAULT_DATE_FROM,
    date_to: DateTo = DEFAULT_DATE_TO,
    region: Regions = (),
    organization: Organizations = (),
    profile: Profile = None,
) -> WaitingSummaryResponse:
    result = service.waiting_summary(
        context,
        _filters(date_from, date_to, Granularity.DAY, region, organization, profile),
    )
    return WaitingSummaryResponse(
        data=WaitingSummaryData(
            waiting_records=_cell(result.waiting_records),
            median_days=_cell(result.median_days),
            p75_days=_cell(result.p75_days),
            p90_days=_cell(result.p90_days),
            oldest_days=_cell(result.oldest_days),
        ),
        meta=_meta(result.metadata),
    )


@router.get("/observed-waiting/summary", response_model=ObservedWaitingResponse)
def observed_waiting(
    context: CurrentUser,
    service: AnalyticsServiceDep,
    date_from: DateFrom = DEFAULT_DATE_FROM,
    date_to: DateTo = DEFAULT_DATE_TO,
    region: Regions = (),
    organization: Organizations = (),
    profile: Profile = None,
) -> ObservedWaitingResponse:
    result = service.observed_waiting(
        context,
        _filters(date_from, date_to, Granularity.DAY, region, organization, profile),
    )
    return ObservedWaitingResponse(
        data=ObservedWaitingData(
            observed_records=_cell(result.observed_records),
            excluded_chronology_conflicts=_cell(result.excluded_chronology_conflicts),
            mean_days=_cell(result.mean_days),
            median_days=_cell(result.median_days),
            p75_days=_cell(result.p75_days),
            p90_days=_cell(result.p90_days),
        ),
        meta=_meta(result.metadata),
    )


@router.get("/organizations", response_model=OrganizationListResponse)
def organizations(
    context: CurrentUser,
    service: AnalyticsServiceDep,
    date_from: DateFrom = DEFAULT_DATE_FROM,
    date_to: DateTo = DEFAULT_DATE_TO,
    region: Regions = (),
    organization: Organizations = (),
    profile: Profile = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> OrganizationListResponse:
    result = service.organizations(
        context,
        _filters(date_from, date_to, Granularity.DAY, region, organization, profile),
        page=page,
        page_size=page_size,
    )
    return OrganizationListResponse(
        data=OrganizationListData(
            items=[_organization(item) for item in result.organizations],
            page=result.page,
            page_size=result.page_size,
            total=result.total,
            has_next=result.page * result.page_size < result.total,
        ),
        meta=_meta(result.metadata),
    )


@router.get(
    "/organizations/{organization_ref}", response_model=OrganizationDetailResponse
)
def organization_detail(
    organization_ref: str,
    context: CurrentUser,
    service: AnalyticsServiceDep,
    date_from: DateFrom = DEFAULT_DATE_FROM,
    date_to: DateTo = DEFAULT_DATE_TO,
) -> OrganizationDetailResponse:
    identity = _identity(organization_ref)
    result = service.organization_detail(
        context,
        identity,
        _filters(date_from, date_to, Granularity.DAY, (), (organization_ref,), None),
    )
    treated = result.treated_snapshot
    return OrganizationDetailResponse(
        data=OrganizationDetailData(
            organization=_organization(result.organization),
            treated_snapshot=(
                TreatedSnapshotResponse(**asdict(treated))
                if treated is not None
                else None
            ),
        ),
        meta=_meta(result.metadata),
    )


@router.get("/data-freshness", response_model=FreshnessResponse)
def freshness(context: CurrentUser, service: AnalyticsServiceDep) -> FreshnessResponse:
    result = service.freshness(context)
    return FreshnessResponse(
        data=[DatasetFreshnessResponse(**asdict(item)) for item in result.datasets],
        meta=_meta(result.metadata),
    )


@router.get("/data-quality", response_model=QualityResponse)
def quality(context: CurrentUser, service: AnalyticsServiceDep) -> QualityResponse:
    result = service.quality(context)
    return QualityResponse(
        data=[DatasetQualityResponse(**asdict(item)) for item in result.datasets],
        meta=_meta(result.metadata),
    )


@router.get("/refusals/breakdown", response_model=BreakdownResponse)
def refusal_breakdown(
    context: CurrentUser,
    service: AnalyticsServiceDep,
    dimension: BreakdownDimension,
    date_from: DateFrom = DEFAULT_DATE_FROM,
    date_to: DateTo = DEFAULT_DATE_TO,
    region: Regions = (),
    organization: Organizations = (),
) -> BreakdownResponse:
    result = service.refusal_breakdown(
        context,
        _filters(date_from, date_to, Granularity.DAY, region, organization, None),
        dimension=dimension,
    )
    return BreakdownResponse(
        data=BreakdownData(
            dimension=result.dimension,
            items=[
                BreakdownItemResponse(label=item.label, count=_cell(item.count))
                for item in result.items
            ],
        ),
        meta=_meta(result.metadata),
    )
