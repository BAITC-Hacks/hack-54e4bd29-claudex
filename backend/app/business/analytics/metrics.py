"""Pure metric semantics and the canonical analytics metric registry."""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from app.business.analytics.contracts import (
    AnalyticsMetadata,
    MetricName,
    ObservedWaitingStatistics,
    OrganizationIdentity,
)
from app.business.analytics.privacy import (
    DEFAULT_SUPPRESSION_THRESHOLD,
    suppress_small_cell,
)
from app.shared.organization_ref import source_organization_digest as _source_digest


class ReferralStatus(StrEnum):
    REFUSED = "REFUSED"
    HOSPITALIZED = "HOSPITALIZED"
    WAITING = "WAITING"
    UNKNOWN = "UNKNOWN"


def source_organization_digest(identity_space: str, normalized_value: str) -> str:
    """Create an opaque, stable URL reference without merging identity spaces."""
    return _source_digest(identity_space, normalized_value)


def classify_referral_status(
    *,
    registration_date: datetime,
    refusal_date: datetime | None,
    hospitalization_date: datetime | None,
) -> ReferralStatus:
    """Apply outcome precedence and reject timestamps before registration."""
    if refusal_date is not None:
        if refusal_date < registration_date:
            return ReferralStatus.UNKNOWN
        return ReferralStatus.REFUSED

    if hospitalization_date is not None:
        if hospitalization_date < registration_date:
            return ReferralStatus.UNKNOWN
        return ReferralStatus.HOSPITALIZED

    return ReferralStatus.WAITING


@dataclass(frozen=True, slots=True)
class ObservedWaitingRecord:
    registration_date: datetime
    hospitalization_date: datetime


def count_represented_organizations(
    identities: Iterable[OrganizationIdentity],
) -> int:
    """Count keys without joining canonical and source identity spaces."""
    return len({identity.key for identity in identities})


def summarize_observed_waiting(
    records: Iterable[ObservedWaitingRecord],
    *,
    metadata: AnalyticsMetadata,
    threshold: int = DEFAULT_SUPPRESSION_THRESHOLD,
) -> ObservedWaitingStatistics:
    """Summarize completed waits, excluding impossible negative durations."""
    waiting_days: list[float] = []
    excluded = 0

    for record in records:
        if record.hospitalization_date < record.registration_date:
            excluded += 1
            continue
        duration = record.hospitalization_date - record.registration_date
        waiting_days.append(duration.total_seconds() / 86_400)

    observed_records = len(waiting_days)
    observed_cell = suppress_small_cell(
        observed_records,
        cell_size=observed_records,
        threshold=threshold,
    )
    excluded_cell = suppress_small_cell(
        excluded,
        cell_size=excluded,
        threshold=threshold,
    )

    if not waiting_days:
        return ObservedWaitingStatistics(
            metadata=metadata,
            observed_records=observed_cell,
            excluded_chronology_conflicts=excluded_cell,
            mean_days=suppress_small_cell(0.0, cell_size=0, threshold=threshold),
            median_days=suppress_small_cell(0.0, cell_size=0, threshold=threshold),
            p75_days=suppress_small_cell(0.0, cell_size=0, threshold=threshold),
            p90_days=suppress_small_cell(0.0, cell_size=0, threshold=threshold),
        )

    ordered = sorted(waiting_days)
    p90_index = math.ceil(0.9 * observed_records) - 1
    p75_index = math.ceil(0.75 * observed_records) - 1
    return ObservedWaitingStatistics(
        metadata=metadata,
        observed_records=observed_cell,
        excluded_chronology_conflicts=excluded_cell,
        mean_days=suppress_small_cell(
            statistics.fmean(ordered),
            cell_size=observed_records,
            threshold=threshold,
        ),
        median_days=suppress_small_cell(
            statistics.median(ordered),
            cell_size=observed_records,
            threshold=threshold,
        ),
        p75_days=suppress_small_cell(
            ordered[p75_index],
            cell_size=observed_records,
            threshold=threshold,
        ),
        p90_days=suppress_small_cell(
            ordered[p90_index],
            cell_size=observed_records,
            threshold=threshold,
        ),
    )


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    name: MetricName
    business_meaning: str
    source: str
    formula: str
    grain: str
    limitations: tuple[str, ...]


_METRIC_DEFINITIONS = {
    MetricName.REFERRALS_TOTAL: MetricDefinition(
        name=MetricName.REFERRALS_TOTAL,
        business_meaning=(
            "Number of referral-event rows registered in the selected period."
        ),
        source="fact_referral_events",
        formula="COUNT(*) WHERE registration_dt is within [date_from, date_to].",
        grain="registration_dt × organization identity",
        limitations=(
            "Counts loaded events; duplicate source rows must be handled upstream.",
        ),
    ),
    MetricName.WAITING_RECORDS: MetricDefinition(
        name=MetricName.WAITING_RECORDS,
        business_meaning=(
            "Number of waiting-event rows represented by the selected snapshot."
        ),
        source="fact_waiting_events",
        formula="COUNT(*) WHERE snapshot_dt equals the selected snapshot_dt.",
        grain="snapshot_dt × organization identity",
        limitations=(
            "Snapshot fact; it is not inferred from referrals without outcomes.",
        ),
    ),
    MetricName.REFUSALS_TOTAL: MetricDefinition(
        name=MetricName.REFUSALS_TOTAL,
        business_meaning=(
            "Number of refusal-event rows whose refuse_dt is in the selected period."
        ),
        source="fact_refusal_events",
        formula="COUNT(*) WHERE refuse_dt is within [date_from, date_to].",
        grain="refuse_dt × organization identity",
        limitations=(
            "Counts refusal events rather than distinct referral registrations.",
        ),
    ),
    MetricName.OBSERVED_WAITING_MEDIAN_DAYS: MetricDefinition(
        name=MetricName.OBSERVED_WAITING_MEDIAN_DAYS,
        business_meaning=(
            "Median elapsed days from referral registration to hospitalization."
        ),
        source=(
            "fact_referral_events.registration_dt + "
            "fact_referral_events.hospitalization_dt"
        ),
        formula=(
            "MEDIAN(hospitalization_dt - registration_dt) in days for "
            "non-negative completed waits."
        ),
        grain="selected period × organization identity",
        limitations=(
            "Excludes incomplete waits and hospitalization timestamps before "
            "registration.",
        ),
    ),
    MetricName.OBSERVED_WAITING_MEAN_DAYS: MetricDefinition(
        name=MetricName.OBSERVED_WAITING_MEAN_DAYS,
        business_meaning=(
            "Mean elapsed days from referral registration to hospitalization."
        ),
        source=(
            "fact_referral_events.registration_dt + "
            "fact_referral_events.hospitalization_dt"
        ),
        formula=(
            "AVG(hospitalization_dt - registration_dt) in days for non-negative "
            "completed waits."
        ),
        grain="selected period × organization identity",
        limitations=("Sensitive to extreme values; excludes chronology conflicts.",),
    ),
    MetricName.OBSERVED_WAITING_P75_DAYS: MetricDefinition(
        name=MetricName.OBSERVED_WAITING_P75_DAYS,
        business_meaning="75th percentile of completed referral waiting time.",
        source=(
            "fact_referral_events.registration_dt + "
            "fact_referral_events.hospitalization_dt"
        ),
        formula=(
            "NEAREST_RANK_P75(hospitalization_dt - registration_dt) in days for "
            "non-negative completed waits."
        ),
        grain="selected period × organization identity",
        limitations=("Excludes incomplete waits and chronology conflicts.",),
    ),
    MetricName.OBSERVED_WAITING_P90_DAYS: MetricDefinition(
        name=MetricName.OBSERVED_WAITING_P90_DAYS,
        business_meaning=(
            "Nearest-rank 90th percentile of elapsed days from registration to "
            "hospitalization."
        ),
        source=(
            "fact_referral_events.registration_dt + "
            "fact_referral_events.hospitalization_dt"
        ),
        formula=(
            "NEAREST_RANK_P90(hospitalization_dt - registration_dt) in days for "
            "non-negative completed waits."
        ),
        grain="selected period × organization identity",
        limitations=(
            "Excludes incomplete waits and hospitalization timestamps before "
            "registration.",
        ),
    ),
    MetricName.QUEUE_AGE_MEDIAN_DAYS: MetricDefinition(
        name=MetricName.QUEUE_AGE_MEDIAN_DAYS,
        business_meaning=(
            "Median age in days of waiting-event rows represented by the selected "
            "snapshot."
        ),
        source="fact_waiting_events",
        formula=(
            "MEDIAN((snapshot_dt - registration_dt) in days) WHERE snapshot_dt "
            "equals the selected snapshot_dt."
        ),
        grain="snapshot_dt × organization identity",
        limitations=(
            "Snapshot fact; negative ages are chronology conflicts and are excluded.",
        ),
    ),
    MetricName.QUEUE_AGE_P75_DAYS: MetricDefinition(
        name=MetricName.QUEUE_AGE_P75_DAYS,
        business_meaning=(
            "75th percentile age in days of waiting-event rows at the selected snapshot."
        ),
        source="fact_waiting_events",
        formula=(
            "NEAREST_RANK_P75((snapshot_dt - registration_dt) in days) WHERE "
            "snapshot_dt equals the selected snapshot_dt."
        ),
        grain="snapshot_dt × organization identity",
        limitations=(
            "Snapshot fact; negative ages are chronology conflicts and are excluded.",
        ),
    ),
    MetricName.QUEUE_AGE_P90_DAYS: MetricDefinition(
        name=MetricName.QUEUE_AGE_P90_DAYS,
        business_meaning=(
            "90th percentile age in days of waiting-event rows at the selected snapshot."
        ),
        source="fact_waiting_events",
        formula=(
            "NEAREST_RANK_P90((snapshot_dt - registration_dt) in days) WHERE "
            "snapshot_dt equals the selected snapshot_dt."
        ),
        grain="snapshot_dt × organization identity",
        limitations=(
            "Snapshot fact; negative ages are chronology conflicts and are excluded.",
        ),
    ),
    MetricName.QUEUE_AGE_OLDEST_DAYS: MetricDefinition(
        name=MetricName.QUEUE_AGE_OLDEST_DAYS,
        business_meaning=(
            "Oldest age in days among waiting-event rows at the selected snapshot."
        ),
        source="fact_waiting_events",
        formula=(
            "MAX((snapshot_dt - registration_dt) in days) WHERE snapshot_dt "
            "equals the selected snapshot_dt."
        ),
        grain="snapshot_dt × organization identity",
        limitations=(
            "Snapshot fact; negative ages are chronology conflicts and are excluded.",
        ),
    ),
}

METRIC_REGISTRY: Mapping[MetricName, MetricDefinition] = MappingProxyType(
    _METRIC_DEFINITIONS
)
