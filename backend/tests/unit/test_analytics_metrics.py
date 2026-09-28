"""Pure analytics contracts, event semantics, and privacy behavior."""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import Any, get_type_hints

import pytest

from app.business.analytics import contracts, metrics
from app.business.analytics.privacy import (
    DEFAULT_SUPPRESSION_THRESHOLD,
    suppress_small_cell,
)
from app.core.exceptions import ValidationError


def _contract(name: str) -> Any:
    contract = getattr(contracts, name, None)
    assert contract is not None, f"analytics contract {name} is required"
    return contract


def _metadata(*, granularity: Any = None, limitations: tuple[str, ...] = ()) -> Any:
    metadata_type = _contract("AnalyticsMetadata")
    return metadata_type(
        date_from=datetime(2025, 1, 1, tzinfo=UTC),
        date_to=datetime(2025, 1, 31, 23, 59, 59, tzinfo=UTC),
        granularity=granularity,
        sources=("fact_referral_events",),
        generated_at=datetime(2025, 2, 1, tzinfo=UTC),
        completed_import_watermark=datetime(2025, 1, 31, 22, 0, tzinfo=UTC),
        limitations=limitations,
    )


def _visible(value: int | float) -> Any:
    return _contract("AnalyticsCell")(value=value, suppressed=False)


def _suppressed() -> Any:
    return _contract("AnalyticsCell")(value=None, suppressed=True)


def test_analytics_filter_accepts_inclusive_366_day_timestamp_range() -> None:
    filters = contracts.AnalyticsFilter(
        date_from=datetime(2024, 1, 1, tzinfo=UTC),
        date_to=datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC),
        granularity=contracts.Granularity.DAY,
    )

    filters.validate()


def test_analytics_filter_rejects_range_longer_than_366_calendar_days() -> None:
    filters = contracts.AnalyticsFilter(
        date_from=datetime(2024, 1, 1, tzinfo=UTC),
        date_to=datetime(2025, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ValidationError) as error:
        filters.validate()

    assert error.value.details == {"max_days": 366, "actual_days": 367}


def test_analytics_filter_rejects_reversed_timestamp_range() -> None:
    filters = contracts.AnalyticsFilter(
        date_from=datetime(2025, 1, 2, tzinfo=UTC),
        date_to=datetime(2025, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ValidationError):
        filters.validate()


def test_organization_identity_supports_canonical_and_source_spaces() -> None:
    identity_type = _contract("OrganizationIdentity")
    identity_space = _contract("OrganizationIdentitySpace")
    mapping_status = _contract("OrganizationMappingStatus")
    organization_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    source_sha256 = "a" * 64

    canonical = identity_type.canonical(organization_id)
    source = identity_type.source(source_sha256)

    assert canonical.key == f"canonical:{organization_id}"
    assert canonical.identity_space is identity_space.CANONICAL
    assert canonical.mapping_status is mapping_status.MAPPED
    assert source.key == f"source:{source_sha256}"
    assert source.identity_space is identity_space.SOURCE
    assert source.mapping_status is mapping_status.UNMAPPED


def test_source_organization_identity_requires_sha256() -> None:
    identity_type = _contract("OrganizationIdentity")

    with pytest.raises(ValueError, match="SHA-256"):
        identity_type.source("not-a-sha256")


@pytest.mark.parametrize(
    ("key", "space_name", "mapping_name"),
    [
        ("source:" + "a" * 64, "CANONICAL", "MAPPED"),
        ("canonical:not-a-uuid", "CANONICAL", "MAPPED"),
        (
            "canonical:11111111-1111-1111-1111-111111111111",
            "SOURCE",
            "MAPPED",
        ),
        ("source:not-a-sha256", "SOURCE", "UNMAPPED"),
        (
            "canonical:11111111-1111-1111-1111-111111111111",
            "CANONICAL",
            "UNMAPPED",
        ),
    ],
)
def test_organization_identity_constructor_enforces_namespace_invariants(
    key: str,
    space_name: str,
    mapping_name: str,
) -> None:
    identity_type = _contract("OrganizationIdentity")
    identity_space = _contract("OrganizationIdentitySpace")
    mapping_status = _contract("OrganizationMappingStatus")

    with pytest.raises(ValueError, match="organization identity"):
        identity_type(
            key=key,
            identity_space=identity_space[space_name],
            mapping_status=mapping_status[mapping_name],
        )


def test_filter_preserves_both_organization_identity_spaces() -> None:
    identity_type = _contract("OrganizationIdentity")
    canonical = identity_type.canonical(uuid.UUID("11111111-1111-1111-1111-111111111111"))
    source = identity_type.source("b" * 64)
    filters = contracts.AnalyticsFilter(
        date_from=datetime(2025, 1, 1, tzinfo=UTC),
        date_to=datetime(2025, 1, 2, tzinfo=UTC),
        organization_ids=(canonical, source),
    )

    assert filters.organization_ids == (canonical, source)


def test_overview_counts_identity_spaces_without_cross_merging() -> None:
    identity_type = _contract("OrganizationIdentity")
    canonical = identity_type.canonical(uuid.UUID("11111111-1111-1111-1111-111111111111"))
    source = identity_type.source("1" * 64)

    represented = metrics.count_represented_organizations((canonical, canonical, source))
    overview = contracts.OverviewResult(
        metadata=_metadata(),
        referrals_total=_visible(20),
        waiting_records=_visible(8),
        refusals_total=_visible(3),
        hospitalized_total=_visible(8),
        unknown_records=_visible(1),
        represented_organizations=_visible(represented),
        represented_regions=_visible(2),
    )

    assert overview.represented_organizations.value == 2
    assert overview.represented_regions.value == 2


def test_common_metadata_carries_provenance_and_completed_import_watermark() -> None:
    metadata = _metadata(
        granularity=contracts.Granularity.WEEK,
        limitations=("Small cells are suppressed.",),
    )

    assert metadata.date_from == datetime(2025, 1, 1, tzinfo=UTC)
    assert metadata.date_to == datetime(2025, 1, 31, 23, 59, 59, tzinfo=UTC)
    assert metadata.granularity is contracts.Granularity.WEEK
    assert metadata.sources == ("fact_referral_events",)
    assert metadata.generated_at == datetime(2025, 2, 1, tzinfo=UTC)
    assert metadata.completed_import_watermark == datetime(2025, 1, 31, 22, 0, tzinfo=UTC)
    assert metadata.limitations == ("Small cells are suppressed.",)


def test_common_metadata_granularity_defaults_to_none() -> None:
    metadata_type = _contract("AnalyticsMetadata")
    metadata = metadata_type(
        date_from=datetime(2025, 1, 1, tzinfo=UTC),
        date_to=datetime(2025, 1, 31, tzinfo=UTC),
        sources=("fact_waiting_events",),
        generated_at=datetime(2025, 2, 1, tzinfo=UTC),
        completed_import_watermark=datetime(2025, 1, 31, tzinfo=UTC),
        limitations=(),
    )

    assert metadata.granularity is None


@pytest.mark.parametrize(
    ("refusal_dt", "hospitalization_dt", "expected_name"),
    [
        (datetime(2025, 1, 3, tzinfo=UTC), None, "REFUSED"),
        (
            datetime(2025, 1, 3, tzinfo=UTC),
            datetime(2025, 1, 4, tzinfo=UTC),
            "REFUSED",
        ),
        (None, datetime(2025, 1, 4, tzinfo=UTC), "HOSPITALIZED"),
        (None, None, "WAITING"),
        (None, datetime(2025, 1, 1, 11, 59, tzinfo=UTC), "UNKNOWN"),
        (datetime(2025, 1, 1, 11, 59, tzinfo=UTC), None, "UNKNOWN"),
    ],
)
def test_referral_status_uses_timestamp_chronology(
    refusal_dt: datetime | None,
    hospitalization_dt: datetime | None,
    expected_name: str,
) -> None:
    status = metrics.classify_referral_status(
        registration_date=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        refusal_date=refusal_dt,
        hospitalization_date=hospitalization_dt,
    )

    assert status.name == expected_name


def test_chronology_contracts_are_typed_as_datetime() -> None:
    record_hints = get_type_hints(metrics.ObservedWaitingRecord)
    classifier_hints = get_type_hints(metrics.classify_referral_status)

    assert record_hints == {
        "registration_date": datetime,
        "hospitalization_date": datetime,
    }
    assert classifier_hints["registration_date"] is datetime
    assert classifier_hints["refusal_date"] == datetime | None
    assert classifier_hints["hospitalization_date"] == datetime | None


def test_observed_waiting_keeps_fractional_days_and_excludes_conflicts() -> None:
    metadata = _metadata()
    start = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    result = metrics.summarize_observed_waiting(
        (
            metrics.ObservedWaitingRecord(start, start),
            metrics.ObservedWaitingRecord(start, start + timedelta(hours=36)),
            metrics.ObservedWaitingRecord(start, start + timedelta(days=9, hours=12)),
            metrics.ObservedWaitingRecord(start, start - timedelta(minutes=1)),
        ),
        metadata=metadata,
        threshold=1,
    )

    assert result.metadata is metadata
    assert result.observed_records.value == 3
    assert result.excluded_chronology_conflicts.value == 1
    assert result.median_days.value == 1.5
    assert result.p90_days.value == 9.5


def test_observed_waiting_uses_default_small_cell_threshold() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    result = metrics.summarize_observed_waiting(
        (metrics.ObservedWaitingRecord(start, start + timedelta(days=2)),),
        metadata=_metadata(),
    )

    assert result.observed_records.suppressed
    assert result.observed_records.value is None
    assert result.median_days.suppressed
    assert result.median_days.value is None


def test_each_observed_waiting_count_uses_its_own_size_for_suppression() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    valid = tuple(
        metrics.ObservedWaitingRecord(start, start + timedelta(days=2)) for _ in range(99)
    )
    conflict = metrics.ObservedWaitingRecord(start, start - timedelta(minutes=1))

    result = metrics.summarize_observed_waiting(
        (*valid, conflict),
        metadata=_metadata(),
    )

    assert result.observed_records.value == 99
    assert not result.observed_records.suppressed
    assert result.excluded_chronology_conflicts.value is None
    assert result.excluded_chronology_conflicts.suppressed


def test_waiting_age_contract_includes_all_required_statistics() -> None:
    waiting = contracts.WaitingAgeStatistics(
        metadata=_metadata(),
        waiting_records=_visible(20),
        median_days=_visible(4.5),
        p75_days=_visible(7.0),
        p90_days=_visible(11.25),
        oldest_days=_visible(32.5),
    )

    assert waiting.median_days.value == 4.5
    assert waiting.p75_days.value == 7.0
    assert waiting.p90_days.value == 11.25
    assert waiting.oldest_days.value == 32.5


def test_suppressed_cell_cannot_carry_an_exact_value() -> None:
    cell_type = _contract("AnalyticsCell")

    with pytest.raises(ValueError, match="suppressed"):
        cell_type(value=42, suppressed=True)


def test_small_sensitive_cell_is_suppressed_without_exact_value() -> None:
    cell_type = _contract("AnalyticsCell")
    cell = suppress_small_cell(42, cell_size=DEFAULT_SUPPRESSION_THRESHOLD - 1)

    assert isinstance(cell, cell_type)
    assert cell.suppressed is True
    assert cell.value is None


def test_cell_at_threshold_keeps_exact_value() -> None:
    cell = suppress_small_cell(42, cell_size=DEFAULT_SUPPRESSION_THRESHOLD)

    assert cell.suppressed is False
    assert cell.value == 42


def test_organization_result_preserves_identity_and_suppression() -> None:
    identity = _contract("OrganizationIdentity").source("c" * 64)
    summary = contracts.OrganizationSummary(
        identity=identity,
        organization_name=None,
        region_id=None,
        referrals_total=_suppressed(),
        waiting_records=_suppressed(),
        refusals_total=_suppressed(),
        observed_waiting_median_days=_suppressed(),
    )
    result_type = _contract("OrganizationSummariesResult")
    result = result_type(metadata=_metadata(), organizations=(summary,))

    assert result.organizations[0].identity.key == f"source:{'c' * 64}"
    assert result.organizations[0].identity.mapping_status.name == "UNMAPPED"
    assert result.organizations[0].waiting_records.suppressed
    assert result.organizations[0].waiting_records.value is None


def test_all_public_result_counts_and_values_use_cells() -> None:
    cell_type = _contract("AnalyticsCell")
    metadata = _metadata(granularity=contracts.Granularity.DAY)
    point = contracts.TimeSeriesPoint(
        period_start=datetime(2025, 1, 1, tzinfo=UTC),
        period_end=datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC),
        value=_suppressed(),
    )
    series = contracts.TimeSeriesResult(
        metadata=metadata,
        metric=metrics.MetricName.REFERRALS_TOTAL,
        points=(point,),
    )
    quality = contracts.QualityResult(
        metadata=metadata,
        records_total=_visible(20),
        records_valid=_visible(18),
        records_invalid=_suppressed(),
        chronology_conflicts=_suppressed(),
        observed_waiting_excluded=_suppressed(),
    )

    assert isinstance(series.points[0].value, cell_type)
    assert series.points[0].value.value is None
    assert series.granularity is contracts.Granularity.DAY
    assert isinstance(quality.records_total, cell_type)
    assert quality.records_invalid.value is None


def test_time_series_requires_granularity_in_metadata() -> None:
    with pytest.raises(ValueError, match="granularity"):
        contracts.TimeSeriesResult(
            metadata=_metadata(),
            metric=metrics.MetricName.REFERRALS_TOTAL,
            points=(),
        )


def test_time_series_metric_uses_neutral_metric_name_contract() -> None:
    metric_name = _contract("MetricName")
    assert metrics.MetricName is metric_name
    assert get_type_hints(contracts.TimeSeriesResult)["metric"] is metric_name


EXPECTED_METRICS = {
    "REFERRALS_TOTAL": {
        "business_meaning": (
            "Number of referral-event rows registered in the selected period."
        ),
        "source": "fact_referral_events",
        "formula": "COUNT(*) WHERE registration_dt is within [date_from, date_to].",
        "grain": "registration_dt × organization identity",
        "limitations": (
            "Counts loaded events; duplicate source rows must be handled upstream.",
        ),
    },
    "WAITING_RECORDS": {
        "business_meaning": (
            "Number of waiting-event rows represented by the selected snapshot."
        ),
        "source": "fact_waiting_events",
        "formula": "COUNT(*) WHERE snapshot_dt equals the selected snapshot_dt.",
        "grain": "snapshot_dt × organization identity",
        "limitations": (
            "Snapshot fact; it is not inferred from referrals without outcomes.",
        ),
    },
    "REFUSALS_TOTAL": {
        "business_meaning": (
            "Number of refusal-event rows whose refuse_dt is in the selected period."
        ),
        "source": "fact_refusal_events",
        "formula": "COUNT(*) WHERE refuse_dt is within [date_from, date_to].",
        "grain": "refuse_dt × organization identity",
        "limitations": (
            "Counts refusal events rather than distinct referral registrations.",
        ),
    },
    "OBSERVED_WAITING_MEDIAN_DAYS": {
        "business_meaning": (
            "Median elapsed days from referral registration to hospitalization."
        ),
        "source": (
            "fact_referral_events.registration_dt + "
            "fact_referral_events.hospitalization_dt"
        ),
        "formula": (
            "MEDIAN(hospitalization_dt - registration_dt) in days for "
            "non-negative completed waits."
        ),
        "grain": "selected period × organization identity",
        "limitations": (
            "Excludes incomplete waits and hospitalization timestamps before "
            "registration.",
        ),
    },
    "OBSERVED_WAITING_P90_DAYS": {
        "business_meaning": (
            "Nearest-rank 90th percentile of elapsed days from registration to "
            "hospitalization."
        ),
        "source": (
            "fact_referral_events.registration_dt + "
            "fact_referral_events.hospitalization_dt"
        ),
        "formula": (
            "NEAREST_RANK_P90(hospitalization_dt - registration_dt) in days for "
            "non-negative completed waits."
        ),
        "grain": "selected period × organization identity",
        "limitations": (
            "Excludes incomplete waits and hospitalization timestamps before "
            "registration.",
        ),
    },
    "QUEUE_AGE_MEDIAN_DAYS": {
        "business_meaning": (
            "Median age in days of waiting-event rows represented by the selected "
            "snapshot."
        ),
        "source": "fact_waiting_events",
        "formula": (
            "MEDIAN((snapshot_dt - registration_dt) in days) WHERE snapshot_dt "
            "equals the selected snapshot_dt."
        ),
        "grain": "snapshot_dt × organization identity",
        "limitations": (
            "Snapshot fact; negative ages are chronology conflicts and are excluded.",
        ),
    },
    "QUEUE_AGE_P75_DAYS": {
        "business_meaning": (
            "75th percentile age in days of waiting-event rows at the selected snapshot."
        ),
        "source": "fact_waiting_events",
        "formula": (
            "NEAREST_RANK_P75((snapshot_dt - registration_dt) in days) WHERE "
            "snapshot_dt equals the selected snapshot_dt."
        ),
        "grain": "snapshot_dt × organization identity",
        "limitations": (
            "Snapshot fact; negative ages are chronology conflicts and are excluded.",
        ),
    },
    "QUEUE_AGE_P90_DAYS": {
        "business_meaning": (
            "90th percentile age in days of waiting-event rows at the selected snapshot."
        ),
        "source": "fact_waiting_events",
        "formula": (
            "NEAREST_RANK_P90((snapshot_dt - registration_dt) in days) WHERE "
            "snapshot_dt equals the selected snapshot_dt."
        ),
        "grain": "snapshot_dt × organization identity",
        "limitations": (
            "Snapshot fact; negative ages are chronology conflicts and are excluded.",
        ),
    },
    "QUEUE_AGE_OLDEST_DAYS": {
        "business_meaning": (
            "Oldest age in days among waiting-event rows at the selected snapshot."
        ),
        "source": "fact_waiting_events",
        "formula": (
            "MAX((snapshot_dt - registration_dt) in days) WHERE snapshot_dt "
            "equals the selected snapshot_dt."
        ),
        "grain": "snapshot_dt × organization identity",
        "limitations": (
            "Snapshot fact; negative ages are chronology conflicts and are excluded.",
        ),
    },
}


def test_metric_registry_has_exact_required_event_semantics() -> None:
    assert set(EXPECTED_METRICS) <= {name.value for name in metrics.METRIC_REGISTRY}

    for name, expected in EXPECTED_METRICS.items():
        definition = metrics.METRIC_REGISTRY[metrics.MetricName(name)]
        assert definition.name.value == name
        assert {
            "business_meaning": definition.business_meaning,
            "source": definition.source,
            "formula": definition.formula,
            "grain": definition.grain,
            "limitations": definition.limitations,
        } == expected


def test_metric_registry_and_result_contracts_are_immutable() -> None:
    with pytest.raises(TypeError):
        metrics.METRIC_REGISTRY[metrics.MetricName.REFERRALS_TOTAL] = (  # type: ignore[index]
            metrics.METRIC_REGISTRY[metrics.MetricName.REFERRALS_TOTAL]
        )

    freshness = contracts.FreshnessResult(
        metadata=_metadata(),
        source="fact_waiting_events",
        latest_record_at=datetime(2025, 1, 31, tzinfo=UTC),
        evaluated_at=datetime(2025, 2, 1, tzinfo=UTC),
    )
    with pytest.raises(FrozenInstanceError):
        freshness.source = "changed"  # type: ignore[misc]


def test_source_organization_digest_is_stable_and_identity_space_specific() -> None:
    first = metrics.source_organization_digest("IS_BG:REFERRALS:RECEIVING", "hospital-a")
    repeated = metrics.source_organization_digest(
        "IS_BG:REFERRALS:RECEIVING", "hospital-a"
    )
    another_space = metrics.source_organization_digest(
        "IS_BG:WAITING:DESTINATION", "hospital-a"
    )

    assert first == repeated
    assert first != another_space
    assert len(first) == 64
    assert "hospital-a" not in first
