"""Framework-free contracts shared by analytics callers and adapters."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Generic, TypeVar

from app.core.exceptions import ValidationError

MAX_DATE_RANGE_DAYS = 366

ValueT = TypeVar("ValueT")


class Granularity(StrEnum):
    """Supported buckets for analytics time series."""

    DAY = "DAY"
    WEEK = "WEEK"


class MetricName(StrEnum):
    REFERRALS_TOTAL = "REFERRALS_TOTAL"
    WAITING_RECORDS = "WAITING_RECORDS"
    REFUSALS_TOTAL = "REFUSALS_TOTAL"
    OBSERVED_WAITING_MEDIAN_DAYS = "OBSERVED_WAITING_MEDIAN_DAYS"
    OBSERVED_WAITING_MEAN_DAYS = "OBSERVED_WAITING_MEAN_DAYS"
    OBSERVED_WAITING_P75_DAYS = "OBSERVED_WAITING_P75_DAYS"
    OBSERVED_WAITING_P90_DAYS = "OBSERVED_WAITING_P90_DAYS"
    QUEUE_AGE_MEDIAN_DAYS = "QUEUE_AGE_MEDIAN_DAYS"
    QUEUE_AGE_P75_DAYS = "QUEUE_AGE_P75_DAYS"
    QUEUE_AGE_P90_DAYS = "QUEUE_AGE_P90_DAYS"
    QUEUE_AGE_OLDEST_DAYS = "QUEUE_AGE_OLDEST_DAYS"


class OrganizationIdentitySpace(StrEnum):
    CANONICAL = "CANONICAL"
    SOURCE = "SOURCE"


class OrganizationMappingStatus(StrEnum):
    MAPPED = "MAPPED"
    UNMAPPED = "UNMAPPED"


@dataclass(frozen=True, slots=True)
class OrganizationIdentity:
    """Stable organization key with its identity namespace and mapping state."""

    key: str
    identity_space: OrganizationIdentitySpace
    mapping_status: OrganizationMappingStatus

    def __post_init__(self) -> None:
        namespace, separator, identity = self.key.partition(":")
        if not separator:
            raise ValueError("organization identity key requires a namespace")

        if self.identity_space is OrganizationIdentitySpace.CANONICAL:
            if namespace != "canonical":
                raise ValueError(
                    "organization identity namespace must match CANONICAL space"
                )
            try:
                canonical_id = uuid.UUID(identity)
            except ValueError as exc:
                raise ValueError(
                    "organization identity canonical key must contain a UUID"
                ) from exc
            if str(canonical_id) != identity.lower():
                raise ValueError(
                    "organization identity canonical key must use canonical UUID form"
                )
            if self.mapping_status is not OrganizationMappingStatus.MAPPED:
                raise ValueError(
                    "organization identity in CANONICAL space must be MAPPED"
                )
            return

        if namespace != "source":
            raise ValueError("organization identity namespace must match SOURCE space")
        if len(identity) != 64 or any(
            character not in "0123456789abcdef" for character in identity
        ):
            raise ValueError(
                "organization identity source key must contain a hexadecimal "
                "SHA-256 digest"
            )

    @classmethod
    def canonical(cls, organization_id: uuid.UUID) -> OrganizationIdentity:
        return cls(
            key=f"canonical:{organization_id}",
            identity_space=OrganizationIdentitySpace.CANONICAL,
            mapping_status=OrganizationMappingStatus.MAPPED,
        )

    @classmethod
    def source(
        cls,
        source_sha256: str,
        *,
        mapping_status: OrganizationMappingStatus = OrganizationMappingStatus.UNMAPPED,
    ) -> OrganizationIdentity:
        normalized_sha256 = source_sha256.lower()
        return cls(
            key=f"source:{normalized_sha256}",
            identity_space=OrganizationIdentitySpace.SOURCE,
            mapping_status=mapping_status,
        )


@dataclass(frozen=True, slots=True)
class AnalyticsCell(Generic[ValueT]):
    """A public metric cell that may hide its exact value."""

    value: ValueT | None
    suppressed: bool

    def __post_init__(self) -> None:
        if self.suppressed and self.value is not None:
            raise ValueError("a suppressed analytics cell cannot contain an exact value")


@dataclass(frozen=True, slots=True)
class AnalyticsFilter:
    """Validated period and optional data-scope filters for analytics queries."""

    date_from: datetime
    date_to: datetime
    granularity: Granularity = Granularity.DAY
    region_ids: tuple[uuid.UUID, ...] = ()
    organization_ids: tuple[OrganizationIdentity, ...] = ()
    profile: str | None = None

    def validate(self, *, max_days: int = MAX_DATE_RANGE_DAYS) -> None:
        if self.date_from > self.date_to:
            raise ValidationError(
                "Начало периода не может быть позже его конца",
                details={
                    "date_from": self.date_from.isoformat(),
                    "date_to": self.date_to.isoformat(),
                },
            )

        actual_days = (self.date_to.date() - self.date_from.date()).days + 1
        if actual_days > max_days:
            raise ValidationError(
                f"Период аналитики не может превышать {max_days} дней",
                details={
                    "max_days": max_days,
                    "actual_days": actual_days,
                },
            )


@dataclass(frozen=True, slots=True)
class AnalyticsMetadata:
    date_from: datetime
    date_to: datetime
    sources: tuple[str, ...]
    generated_at: datetime
    completed_import_watermark: datetime | None
    limitations: tuple[str, ...]
    granularity: Granularity | None = None
    latest_import_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OverviewResult:
    metadata: AnalyticsMetadata
    referrals_total: AnalyticsCell[int]
    waiting_records: AnalyticsCell[int]
    refusals_total: AnalyticsCell[int]
    hospitalized_total: AnalyticsCell[int]
    unknown_records: AnalyticsCell[int]
    represented_organizations: AnalyticsCell[int]
    represented_regions: AnalyticsCell[int]


@dataclass(frozen=True, slots=True)
class TimeSeriesPoint:
    period_start: datetime
    period_end: datetime
    value: AnalyticsCell[int | float]


@dataclass(frozen=True, slots=True)
class TimeSeriesResult:
    metadata: AnalyticsMetadata
    metric: MetricName
    points: tuple[TimeSeriesPoint, ...]

    def __post_init__(self) -> None:
        if self.metadata.granularity is None:
            raise ValueError("time-series metadata requires granularity")

    @property
    def granularity(self) -> Granularity:
        granularity = self.metadata.granularity
        if granularity is None:
            raise ValueError("time-series metadata requires granularity")
        return granularity


@dataclass(frozen=True, slots=True)
class WaitingAgeStatistics:
    metadata: AnalyticsMetadata
    waiting_records: AnalyticsCell[int]
    median_days: AnalyticsCell[int | float]
    p75_days: AnalyticsCell[int | float]
    p90_days: AnalyticsCell[int | float]
    oldest_days: AnalyticsCell[int | float]


@dataclass(frozen=True, slots=True)
class ObservedWaitingStatistics:
    metadata: AnalyticsMetadata
    observed_records: AnalyticsCell[int]
    excluded_chronology_conflicts: AnalyticsCell[int]
    mean_days: AnalyticsCell[int | float]
    median_days: AnalyticsCell[int | float]
    p75_days: AnalyticsCell[int | float]
    p90_days: AnalyticsCell[int | float]


@dataclass(frozen=True, slots=True)
class OrganizationSummary:
    identity: OrganizationIdentity
    organization_name: str | None
    region_id: uuid.UUID | None
    referrals_total: AnalyticsCell[int]
    waiting_records: AnalyticsCell[int]
    refusals_total: AnalyticsCell[int]
    observed_waiting_median_days: AnalyticsCell[int | float]
    source_system: str | None = None
    identity_label: str | None = None
    canonical_hospital_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class TreatedSnapshot:
    snapshot_load_dt: datetime
    discharged_total: int
    discharged_children: int
    treated_budget: int
    treated_paid: int
    discharged_within_day: int
    deaths_total: int
    bed_days: int
    amount_to_pay: float


@dataclass(frozen=True, slots=True)
class OrganizationDetail:
    metadata: AnalyticsMetadata
    organization: OrganizationSummary
    treated_snapshot: TreatedSnapshot | None


@dataclass(frozen=True, slots=True)
class OrganizationSummariesResult:
    metadata: AnalyticsMetadata
    organizations: tuple[OrganizationSummary, ...]
    page: int = 1
    page_size: int = 20
    total: int = 0


@dataclass(frozen=True, slots=True)
class FreshnessResult:
    metadata: AnalyticsMetadata
    source: str
    latest_record_at: datetime | None
    evaluated_at: datetime


class FreshnessStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class DatasetFreshness:
    dataset_type: str
    event_period_start: datetime | None
    event_period_end: datetime | None
    source_load_date: datetime | None
    last_successful_import: datetime | None
    status: FreshnessStatus
    explanation: str | None


@dataclass(frozen=True, slots=True)
class FreshnessOverview:
    metadata: AnalyticsMetadata
    datasets: tuple[DatasetFreshness, ...]


@dataclass(frozen=True, slots=True)
class QualityResult:
    metadata: AnalyticsMetadata
    records_total: AnalyticsCell[int]
    records_valid: AnalyticsCell[int]
    records_invalid: AnalyticsCell[int]
    chronology_conflicts: AnalyticsCell[int]
    observed_waiting_excluded: AnalyticsCell[int]


@dataclass(frozen=True, slots=True)
class DatasetQualitySummary:
    dataset_type: str
    status: str
    rows_loaded: int
    warnings_count: int
    rejected_count: int
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QualityOverview:
    metadata: AnalyticsMetadata
    datasets: tuple[DatasetQualitySummary, ...]


@dataclass(frozen=True, slots=True)
class BreakdownCell:
    label: str
    count: AnalyticsCell[int]


@dataclass(frozen=True, slots=True)
class BreakdownResult:
    metadata: AnalyticsMetadata
    dimension: str
    items: tuple[BreakdownCell, ...]
