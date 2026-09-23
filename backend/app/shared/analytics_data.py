"""Neutral records exchanged across analytics ports and adapters."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class QueryScope:
    canonical_hospital_ids: tuple[uuid.UUID, ...]
    all_canonical: bool
    include_unmapped: bool
    mapping_version: str | None = None
    published_import_ids: tuple[uuid.UUID, ...] | None = None


@dataclass(frozen=True, slots=True)
class ImportWatermark:
    completed_at: datetime | None
    import_ids: tuple[uuid.UUID, ...]
    mapping_version: str | None = None
    mapping_generation: int = 0
    mapping_verified: bool = False


@dataclass(frozen=True, slots=True)
class RawOverview:
    referrals_total: int
    waiting_records: int
    refusals_total: int
    hospitalized_total: int
    unknown_records: int
    represented_organizations: int
    represented_regions: int


@dataclass(frozen=True, slots=True)
class RawTimeSeriesPoint:
    period_start: datetime
    value: int


@dataclass(frozen=True, slots=True)
class RawWaitingSummary:
    snapshot_dt: datetime | None
    waiting_records: int
    excluded_chronology_conflicts: int
    median_days: float | None
    p75_days: float | None
    p90_days: float | None
    oldest_days: float | None


@dataclass(frozen=True, slots=True)
class RawObservedWaiting:
    observed_records: int
    excluded_chronology_conflicts: int
    mean_days: float | None
    median_days: float | None
    p75_days: float | None
    p90_days: float | None


@dataclass(frozen=True, slots=True)
class RawOrganization:
    identity_space: str
    source_system: str
    source_value: str
    canonical_hospital_id: uuid.UUID | None
    referrals_total: int
    waiting_records: int
    refusals_total: int
    observed_waiting_median_days: float | None


@dataclass(frozen=True, slots=True)
class RawTreatedSnapshot:
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
class RawDatasetCoverage:
    dataset_type: str
    event_period_start: datetime | None
    event_period_end: datetime | None
    source_load_date: datetime | None


@dataclass(frozen=True, slots=True)
class RawBreakdownCell:
    label: str
    count: int


@dataclass(frozen=True, slots=True)
class ImportSummary:
    dataset_type: str
    source: str
    import_id: uuid.UUID
    completed_at: datetime
    rows_loaded: int
    rows_rejected: int
    warnings_count: int
    quality_issues: tuple[str, ...] = ()
    completeness: str = "UNKNOWN"
