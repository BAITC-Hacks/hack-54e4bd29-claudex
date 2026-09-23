"""Business orchestration for descriptive analytics."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any, TypeVar

from app.business.analytics.contracts import (
    AnalyticsCell,
    AnalyticsFilter,
    AnalyticsMetadata,
    BreakdownCell,
    BreakdownResult,
    DatasetFreshness,
    DatasetQualitySummary,
    FreshnessOverview,
    FreshnessStatus,
    MetricName,
    ObservedWaitingStatistics,
    OrganizationDetail,
    OrganizationIdentity,
    OrganizationIdentitySpace,
    OrganizationMappingStatus,
    OrganizationSummariesResult,
    OrganizationSummary,
    OverviewResult,
    QualityOverview,
    TimeSeriesPoint,
    TimeSeriesResult,
    TreatedSnapshot,
    WaitingAgeStatistics,
)
from app.business.analytics.metrics import source_organization_digest
from app.business.analytics.ports import (
    AnalyticsCache,
    AnalyticsMetadataRepository,
    AnalyticsRepository,
    ImportWatermark,
    QueryScope,
    RawOrganization,
)
from app.business.analytics.privacy import suppress_small_cell
from app.core.analytics_metrics import (
    observe_analytics_query,
    record_analytics_cache,
)
from app.core.exceptions import DependencyUnavailableError, NotFoundError
from app.security.authorization import AuthorizationService
from app.security.context import Role, SecurityContext
from app.security.permissions import Permission
from app.shared.delivery import DeliveryReadiness

GOVERNANCE_ROLES = frozenset({Role.ADMIN, Role.HEALTH_AUTHORITY})
OVERVIEW_SOURCES = ("ИС БГ:REFERRALS", "ИС БГ:WAITING", "ИС БГ:REFUSALS")
MAPPING_LIMITATION = "Сопоставление организаций неполное."
WAITING_LIMITATION = (
    "Данные ожидания являются предоставленным срезом, а не историей очереди."
)
TREATED_LIMITATION = (
    "Показатели пролеченных случаев являются предоставленным срезом; "
    "отчётный период не подтверждён."
)

ValueT = TypeVar("ValueT", int, float)
logger = logging.getLogger(__name__)


def _exact(value: ValueT | None) -> AnalyticsCell[ValueT]:
    return AnalyticsCell(value=value, suppressed=False)


def classify_freshness(readiness: DeliveryReadiness, now: datetime) -> FreshnessStatus:
    if readiness.completeness == "PARTIAL":
        return FreshnessStatus.PARTIAL
    if readiness.cadence_days is None or readiness.confirmed_complete_through is None:
        return FreshnessStatus.UNKNOWN
    return (
        FreshnessStatus.CURRENT
        if (now.date() - readiness.confirmed_complete_through).days
        <= readiness.cadence_days
        else FreshnessStatus.STALE
    )


def publication_snapshot(method: Callable[..., Any]) -> Callable[..., Any]:
    """One immutable PG read snapshot per response, rechecked after cache/query."""

    @wraps(method)
    def checked(
        self: AnalyticsService, context: SecurityContext, *args: Any, **kwargs: Any
    ) -> Any:
        self._authorization.require_permission(context, Permission.ANALYTICS_READ)
        watermark = self._metadata.latest_completed_imports()
        if (
            not (context.scope.resolved and context.scope.is_global)
            and not watermark.mapping_verified
        ):
            raise DependencyUnavailableError("MAPPING_PUBLICATION_UNAVAILABLE")
        token = self._read_watermark.set(watermark)
        try:
            result = method(self, context, *args, **kwargs)
            if self._metadata.latest_completed_imports() != watermark:
                raise DependencyUnavailableError("PUBLICATION_CHANGED_RETRY")
            return result
        finally:
            self._read_watermark.reset(token)

    return checked


class AnalyticsService:
    """Apply permissions, data scope and cache isolation around aggregates."""

    def __init__(
        self,
        *,
        repository: AnalyticsRepository,
        metadata_repository: AnalyticsMetadataRepository,
        cache: AnalyticsCache,
        authorization: AuthorizationService,
        min_cell_size: int,
        cache_ttl_seconds: int,
        max_date_range_days: int = 366,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._read_watermark: ContextVar[ImportWatermark | None] = ContextVar(
            "analytics_publication", default=None
        )
        self._repository = repository
        self._metadata = metadata_repository
        self._cache = cache
        self._authorization = authorization
        self._min_cell_size = min_cell_size
        self._cache_ttl_seconds = cache_ttl_seconds
        self._max_date_range_days = max_date_range_days
        self._clock = clock or (lambda: datetime.now(UTC))

    def _watermark(self) -> ImportWatermark:
        current = self._read_watermark.get()
        return (
            current if current is not None else self._metadata.latest_completed_imports()
        )

    def _publication_scope(self, scope: QueryScope) -> QueryScope:
        watermark = self._watermark()
        if not scope.all_canonical and not watermark.mapping_verified:
            raise DependencyUnavailableError("MAPPING_PUBLICATION_UNAVAILABLE")
        return replace(
            scope,
            mapping_version=watermark.mapping_version,
            published_import_ids=watermark.import_ids,
        )

    def _query_scope(
        self,
        context: SecurityContext,
        filters: AnalyticsFilter | None = None,
    ) -> QueryScope:
        direct = tuple(
            sorted((uuid.UUID(item) for item in context.scope.hospital_ids), key=str)
        )
        context_regions = tuple(
            sorted((uuid.UUID(item) for item in context.scope.region_ids), key=str)
        )
        regional = self._metadata.hospital_ids_for_regions(context_regions)

        if context.scope.is_global and context.scope.resolved:
            scope = QueryScope((), all_canonical=True, include_unmapped=True)
        else:
            canonical_ids = tuple(dict.fromkeys((*direct, *regional)))
            scope = QueryScope(
                canonical_hospital_ids=canonical_ids,
                all_canonical=False,
                include_unmapped=False,
            )

        if filters is None:
            return self._publication_scope(scope)

        requested_hospitals = {
            uuid.UUID(item.key.removeprefix("canonical:"))
            for item in filters.organization_ids
            if item.identity_space is OrganizationIdentitySpace.CANONICAL
        }
        if filters.region_ids:
            requested_hospitals.update(
                self._metadata.hospital_ids_for_regions(filters.region_ids)
            )
        has_canonical_constraint = bool(filters.region_ids) or any(
            item.identity_space is OrganizationIdentitySpace.CANONICAL
            for item in filters.organization_ids
        )
        if not requested_hospitals and has_canonical_constraint:
            return self._publication_scope(
                QueryScope((), all_canonical=False, include_unmapped=False)
            )
        if not requested_hospitals:
            return self._publication_scope(scope)

        if scope.all_canonical:
            narrowed = tuple(sorted(requested_hospitals, key=str))
        else:
            narrowed = tuple(
                item
                for item in scope.canonical_hospital_ids
                if item in requested_hospitals
            )
        return self._publication_scope(
            QueryScope(
                canonical_hospital_ids=narrowed,
                all_canonical=False,
                include_unmapped=(
                    scope.include_unmapped
                    and not filters.region_ids
                    and any(
                        item.identity_space is OrganizationIdentitySpace.SOURCE
                        for item in filters.organization_ids
                    )
                ),
            )
        )

    def _authorize(self, context: SecurityContext, filters: AnalyticsFilter) -> None:
        self._authorization.require_permission(context, Permission.ANALYTICS_READ)
        filters.validate(max_days=self._max_date_range_days)
        for identity in filters.organization_ids:
            self.require_organization_access(context, identity)
        if not (context.scope.is_global and context.scope.resolved):
            for region_id in filters.region_ids:
                self._authorization.require_region_access(context, region_id)

    def require_organization_access(
        self, context: SecurityContext, identity: OrganizationIdentity
    ) -> None:
        if identity.identity_space is OrganizationIdentitySpace.SOURCE:
            if not (context.scope.resolved and context.scope.is_global):
                raise NotFoundError("Организация не найдена")
            return

        hospital_id = uuid.UUID(identity.key.removeprefix("canonical:"))
        scope = self._query_scope(context)
        if not scope.all_canonical and hospital_id not in scope.canonical_hospital_ids:
            raise NotFoundError("Организация не найдена")

    def _cache_key(
        self,
        endpoint: str,
        filters: AnalyticsFilter,
        scope: QueryScope,
        watermark: ImportWatermark,
    ) -> str:
        material = {
            "endpoint": endpoint,
            "mapping_version": watermark.mapping_version,
            "mapping_generation": watermark.mapping_generation,
            "date_from": filters.date_from.isoformat(),
            "date_to": filters.date_to.isoformat(),
            "granularity": filters.granularity.value,
            "region_ids": sorted(str(item) for item in filters.region_ids),
            "organization_ids": sorted(item.key for item in filters.organization_ids),
            "profile": filters.profile,
            "scope": {
                "hospitals": sorted(str(item) for item in scope.canonical_hospital_ids),
                "all_canonical": scope.all_canonical,
                "include_unmapped": scope.include_unmapped,
            },
            "watermark": {
                "completed_at": (
                    watermark.completed_at.isoformat()
                    if watermark.completed_at is not None
                    else None
                ),
                "import_ids": sorted(str(item) for item in watermark.import_ids),
            },
        }
        digest = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f"medsignal:analytics:{endpoint}:{digest}"

    def _metadata_for(
        self,
        filters: AnalyticsFilter,
        watermark: ImportWatermark,
        *,
        sources: tuple[str, ...] = OVERVIEW_SOURCES,
        limitations: tuple[str, ...] = (),
        time_series: bool = False,
    ) -> AnalyticsMetadata:
        return AnalyticsMetadata(
            date_from=filters.date_from,
            date_to=filters.date_to,
            sources=sources,
            generated_at=self._clock(),
            completed_import_watermark=watermark.completed_at,
            limitations=limitations,
            granularity=filters.granularity if time_series else None,
            latest_import_ids=tuple(str(item) for item in watermark.import_ids),
            mapping_version=watermark.mapping_version,
            mapping_publication_available=watermark.mapping_verified,
        )

    @publication_snapshot
    def overview(
        self, context: SecurityContext, filters: AnalyticsFilter
    ) -> OverviewResult:
        self._authorize(context, filters)
        scope = self._query_scope(context, filters)
        watermark = self._watermark()
        key = self._cache_key("overview", filters, scope, watermark)
        try:
            raw = self._cache.get_overview(key)
        except Exception:  # cache is an optional accelerator
            logger.warning("analytics_cache_read_failed")
            record_analytics_cache("overview", "error")
            raw = None
        else:
            record_analytics_cache("overview", "hit" if raw is not None else "miss")
        if raw is None:
            with observe_analytics_query("overview"):
                raw = self._repository.overview(filters, scope)
            try:
                self._cache.set_overview(key, raw, self._cache_ttl_seconds)
            except Exception:
                logger.warning("analytics_cache_write_failed")

        return OverviewResult(
            metadata=self._metadata_for(
                filters, watermark, limitations=(MAPPING_LIMITATION,)
            ),
            referrals_total=_exact(raw.referrals_total),
            waiting_records=_exact(raw.waiting_records),
            refusals_total=_exact(raw.refusals_total),
            hospitalized_total=_exact(raw.hospitalized_total),
            unknown_records=_exact(raw.unknown_records),
            represented_organizations=_exact(raw.represented_organizations),
            represented_regions=_exact(raw.represented_regions),
        )

    def _timeseries(
        self,
        context: SecurityContext,
        filters: AnalyticsFilter,
        *,
        metric: MetricName,
    ) -> TimeSeriesResult:
        self._authorize(context, filters)
        scope = self._query_scope(context, filters)
        if metric is MetricName.REFERRALS_TOTAL:
            with observe_analytics_query("referral_timeseries"):
                rows = self._repository.referral_timeseries(filters, scope)
            sources = ("ИС БГ:REFERRALS",)
        else:
            with observe_analytics_query("refusal_timeseries"):
                rows = self._repository.refusal_timeseries(filters, scope)
            sources = ("ИС БГ:REFUSALS",)
        delta = timedelta(days=1 if filters.granularity.value == "DAY" else 7)
        watermark = self._watermark()
        return TimeSeriesResult(
            metadata=self._metadata_for(
                filters,
                watermark,
                sources=sources,
                limitations=(MAPPING_LIMITATION,),
                time_series=True,
            ),
            metric=metric,
            points=tuple(
                TimeSeriesPoint(
                    row.period_start,
                    row.period_start + delta,
                    _exact(row.value),
                )
                for row in rows
            ),
        )

    @publication_snapshot
    def referral_timeseries(
        self, context: SecurityContext, filters: AnalyticsFilter
    ) -> TimeSeriesResult:
        return self._timeseries(context, filters, metric=MetricName.REFERRALS_TOTAL)

    @publication_snapshot
    def refusal_timeseries(
        self, context: SecurityContext, filters: AnalyticsFilter
    ) -> TimeSeriesResult:
        return self._timeseries(context, filters, metric=MetricName.REFUSALS_TOTAL)

    @publication_snapshot
    def waiting_summary(
        self, context: SecurityContext, filters: AnalyticsFilter
    ) -> WaitingAgeStatistics:
        self._authorize(context, filters)
        readiness = self._metadata.delivery_readiness("WAITING")
        scope = self._query_scope(context, filters)
        snapshot_approved = bool(readiness.snapshot_approved_import_ids)
        if snapshot_approved:
            scope = replace(
                scope,
                published_import_ids=tuple(
                    i
                    for i in scope.published_import_ids or ()
                    if i in readiness.snapshot_approved_import_ids
                ),
            )
        with observe_analytics_query("waiting_summary"):
            raw = self._repository.waiting_summary(filters, scope)
        watermark = self._watermark()
        return WaitingAgeStatistics(
            metadata=self._metadata_for(
                filters,
                watermark,
                sources=("ИС БГ:WAITING",),
                limitations=(WAITING_LIMITATION, MAPPING_LIMITATION)
                + (() if snapshot_approved else ("SNAPSHOT_SEMANTICS_UNCONFIRMED",)),
            ),
            waiting_records=_exact(raw.waiting_records),
            median_days=_exact(raw.median_days if snapshot_approved else None),
            p75_days=_exact(raw.p75_days if snapshot_approved else None),
            p90_days=_exact(raw.p90_days if snapshot_approved else None),
            oldest_days=_exact(raw.oldest_days if snapshot_approved else None),
        )

    @publication_snapshot
    def observed_waiting(
        self, context: SecurityContext, filters: AnalyticsFilter
    ) -> ObservedWaitingStatistics:
        self._authorize(context, filters)
        with observe_analytics_query("observed_waiting"):
            raw = self._repository.observed_waiting(
                filters, self._query_scope(context, filters)
            )
        watermark = self._watermark()
        return ObservedWaitingStatistics(
            metadata=self._metadata_for(
                filters,
                watermark,
                sources=("ИС БГ:REFERRALS",),
                limitations=(
                    "Показатель описывает завершённые госпитализации "
                    "и не является прогнозом.",
                ),
            ),
            observed_records=_exact(raw.observed_records),
            excluded_chronology_conflicts=_exact(raw.excluded_chronology_conflicts),
            mean_days=_exact(raw.mean_days),
            median_days=_exact(raw.median_days),
            p75_days=_exact(raw.p75_days),
            p90_days=_exact(raw.p90_days),
        )

    def _organization_summary(self, raw: RawOrganization) -> OrganizationSummary:
        if raw.canonical_hospital_id is not None:
            identity = OrganizationIdentity.canonical(raw.canonical_hospital_id)
            name = self._metadata.hospital_name(raw.canonical_hospital_id)
            label = name
        else:
            identity = OrganizationIdentity.source(
                source_organization_digest(raw.identity_space, raw.source_value),
                mapping_status=OrganizationMappingStatus.UNMAPPED,
            )
            name = raw.source_value
            label = "Организация не сопоставлена"
        return OrganizationSummary(
            identity=identity,
            organization_name=name,
            region_id=None,
            referrals_total=_exact(raw.referrals_total),
            waiting_records=_exact(raw.waiting_records),
            refusals_total=_exact(raw.refusals_total),
            observed_waiting_median_days=_exact(raw.observed_waiting_median_days),
            source_system=raw.source_system,
            identity_label=label,
            canonical_hospital_id=raw.canonical_hospital_id,
        )

    @publication_snapshot
    def organizations(
        self,
        context: SecurityContext,
        filters: AnalyticsFilter,
        *,
        page: int,
        page_size: int,
    ) -> OrganizationSummariesResult:
        self._authorize(context, filters)
        with observe_analytics_query("organizations"):
            rows, total = self._repository.organizations(
                filters,
                self._query_scope(context, filters),
                limit=page_size,
                offset=(page - 1) * page_size,
            )
        watermark = self._watermark()
        return OrganizationSummariesResult(
            metadata=self._metadata_for(
                filters, watermark, limitations=(MAPPING_LIMITATION,)
            ),
            organizations=tuple(self._organization_summary(row) for row in rows),
            page=page,
            page_size=page_size,
            total=total,
        )

    @publication_snapshot
    def organization_detail(
        self,
        context: SecurityContext,
        identity: OrganizationIdentity,
        filters: AnalyticsFilter,
    ) -> OrganizationDetail:
        self._authorize(context, filters)
        self.require_organization_access(context, identity)
        with observe_analytics_query("organization_detail"):
            result = self._repository.organization_detail(
                identity.key, filters, self._query_scope(context, filters)
            )
        if result is None:
            raise NotFoundError("Организация не найдена")
        raw, treated = result
        watermark = self._watermark()
        return OrganizationDetail(
            metadata=self._metadata_for(
                filters,
                watermark,
                limitations=(MAPPING_LIMITATION, TREATED_LIMITATION),
            ),
            organization=self._organization_summary(raw),
            treated_snapshot=(
                TreatedSnapshot(
                    snapshot_load_dt=treated.snapshot_load_dt,
                    discharged_total=treated.discharged_total,
                    discharged_children=treated.discharged_children,
                    treated_budget=treated.treated_budget,
                    treated_paid=treated.treated_paid,
                    discharged_within_day=treated.discharged_within_day,
                    deaths_total=treated.deaths_total,
                    bed_days=treated.bed_days,
                    amount_to_pay=treated.amount_to_pay,
                )
                if treated is not None
                else None
            ),
        )

    @publication_snapshot
    def freshness(self, context: SecurityContext) -> FreshnessOverview:
        self._authorization.require_permission(context, Permission.ANALYTICS_READ)
        with observe_analytics_query("data_freshness"):
            coverage = self._repository.dataset_coverage(self._query_scope(context))
        imports = {
            item.dataset_type: item for item in self._metadata.latest_import_summaries()
        }
        now = self._clock()
        readiness = {
            row.dataset_type: self._metadata.delivery_readiness(row.dataset_type)
            for row in coverage
        }
        fallback = AnalyticsFilter(now, now)
        watermark = self._watermark()
        return FreshnessOverview(
            metadata=self._metadata_for(fallback, watermark),
            datasets=tuple(
                DatasetFreshness(
                    dataset_type=row.dataset_type,
                    event_period_start=row.event_period_start,
                    event_period_end=row.event_period_end,
                    source_load_date=row.source_load_date,
                    last_successful_import=(
                        imports[row.dataset_type].completed_at
                        if row.dataset_type in imports
                        else None
                    ),
                    status=classify_freshness(readiness[row.dataset_type], now),
                    explanation=readiness[row.dataset_type].reason
                    or (
                        "Периодичность поставки данных не определена."
                        if readiness[row.dataset_type].cadence_days is None
                        else None
                    ),
                    confirmed_complete_through=readiness[
                        row.dataset_type
                    ].confirmed_complete_through,
                    cadence_known=readiness[row.dataset_type].cadence_days is not None,
                    completeness=readiness[row.dataset_type].completeness,
                    forecast_available=False,
                )
                for row in coverage
            ),
        )

    @publication_snapshot
    def quality(self, context: SecurityContext) -> QualityOverview:
        self._authorization.require_permission(context, Permission.ANALYTICS_READ)
        now = self._clock()
        fallback = AnalyticsFilter(now, now)
        watermark = self._watermark()
        if not (context.scope.resolved and context.scope.is_global):
            return QualityOverview(
                metadata=self._metadata_for(
                    fallback, watermark, limitations=("GLOBAL_QUALITY_TOTALS_RESTRICTED",)
                ),
                datasets=(),
            )
        datasets = tuple(
            DatasetQualitySummary(
                dataset_type=item.dataset_type,
                status=(
                    "PARTIAL"
                    if item.completeness == "PARTIAL"
                    else "WARNING"
                    if item.warnings_count
                    else "LOADED"
                ),
                rows_loaded=item.rows_loaded,
                warnings_count=item.warnings_count,
                rejected_count=item.rows_rejected,
                issues=item.quality_issues
                + (("INCOMPLETE_DELIVERY",) if item.completeness == "PARTIAL" else ()),
            )
            for item in self._metadata.latest_import_summaries()
        )
        return QualityOverview(
            metadata=self._metadata_for(fallback, watermark), datasets=datasets
        )

    @publication_snapshot
    def refusal_breakdown(
        self,
        context: SecurityContext,
        filters: AnalyticsFilter,
        *,
        dimension: str,
    ) -> BreakdownResult:
        self._authorize(context, filters)
        with observe_analytics_query("refusal_breakdown"):
            rows = self._repository.refusal_breakdown(
                filters, self._query_scope(context, filters), dimension=dimension
            )
        watermark = self._watermark()
        sensitive = dimension in {
            "resident",
            "insured",
            "benefit_category",
            "icd_group",
        }
        return BreakdownResult(
            metadata=self._metadata_for(filters, watermark, sources=("ИС БГ:REFUSALS",)),
            dimension=dimension,
            items=tuple(
                BreakdownCell(
                    label=row.label,
                    count=(
                        suppress_small_cell(
                            row.count,
                            cell_size=row.count,
                            threshold=self._min_cell_size,
                        )
                        if sensitive
                        else _exact(row.count)
                    ),
                )
                for row in rows
            ),
        )
