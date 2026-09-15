"""ClickHouse analytics repository returns aggregates and parameterizes input."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.business.analytics.contracts import (
    AnalyticsFilter,
    Granularity,
    OrganizationIdentity,
)
from app.business.analytics.ports import QueryScope
from app.repositories.clickhouse_analytics import ClickHouseAnalyticsRepository


class RecordingClient:
    def __init__(self, rows_by_marker: dict[str, list[tuple]]) -> None:
        self.rows_by_marker = rows_by_marker
        self.calls: list[tuple[str, dict[str, object]]] = []

    def query(self, query: str, parameters: dict[str, object] | None = None):
        actual = parameters or {}
        self.calls.append((query, actual))
        rows: list[tuple] = []
        for marker, candidate in self.rows_by_marker.items():
            if marker in query:
                rows = candidate
                break
        return SimpleNamespace(result_rows=rows)


def filters(*, profile: str | None = None) -> AnalyticsFilter:
    return AnalyticsFilter(
        date_from=datetime(2025, 1, 1, tzinfo=UTC),
        date_to=datetime(2025, 3, 31, 23, 59, 59, tzinfo=UTC),
        granularity=Granularity.DAY,
        profile=profile,
    )


def test_referral_timeseries_uses_aggregates_and_parameterizes_profile() -> None:
    profile = "cardiology') OR 1=1 --"
    client = RecordingClient(
        {"analytics:referral-timeseries": [(datetime(2025, 1, 1), 11)]}
    )
    repository = ClickHouseAnalyticsRepository(client)

    points = repository.referral_timeseries(
        filters(profile=profile),
        QueryScope((), all_canonical=True, include_unmapped=True),
    )

    assert [(point.period_start, point.value) for point in points] == [
        (datetime(2025, 1, 1), 11)
    ]
    query, parameters = client.calls[0]
    assert profile not in query
    assert parameters["profile"] == profile
    assert "GROUP BY" in query


def test_bounded_scope_is_passed_as_uuid_array_and_never_interpolated() -> None:
    hospital_id = uuid.uuid4()
    client = RecordingClient(
        {"analytics:refusal-timeseries": [(datetime(2025, 1, 2), 3)]}
    )
    repository = ClickHouseAnalyticsRepository(client)

    repository.refusal_timeseries(
        filters(),
        QueryScope((hospital_id,), all_canonical=False, include_unmapped=False),
    )

    query, parameters = client.calls[0]
    assert str(hospital_id) not in query
    assert parameters["hospital_ids"] == [str(hospital_id)]
    assert "hospital_id IS NOT NULL" in query


def test_waiting_summary_uses_latest_snapshot_and_reports_all_age_quantiles() -> None:
    snapshot = datetime(2026, 5, 13, tzinfo=UTC)
    client = RecordingClient(
        {"analytics:waiting-summary": [(snapshot, 100, 2, 10.5, 20.5, 30.5, 90.0)]}
    )
    repository = ClickHouseAnalyticsRepository(client)

    result = repository.waiting_summary(
        filters(), QueryScope((), all_canonical=True, include_unmapped=True)
    )

    assert result.snapshot_dt == snapshot
    assert result.waiting_records == 100
    assert result.excluded_chronology_conflicts == 2
    assert result.median_days == 10.5
    assert result.p75_days == 20.5
    assert result.p90_days == 30.5
    assert result.oldest_days == 90.0


def test_observed_waiting_reports_mean_and_excluded_chronology() -> None:
    client = RecordingClient(
        {"analytics:observed-waiting": [(80, 12, 5.5, 4.0, 7.0, 11.0)]}
    )
    repository = ClickHouseAnalyticsRepository(client)

    result = repository.observed_waiting(
        filters(), QueryScope((), all_canonical=True, include_unmapped=True)
    )

    assert result.observed_records == 80
    assert result.excluded_chronology_conflicts == 12
    assert result.mean_days == 5.5
    assert result.median_days == 4.0
    assert result.p75_days == 7.0
    assert result.p90_days == 11.0


def test_source_organization_filter_uses_digest_parameter_not_raw_sql() -> None:
    digest = "a" * 64
    source_filter = AnalyticsFilter(
        date_from=datetime(2025, 1, 1, tzinfo=UTC),
        date_to=datetime(2025, 3, 31, tzinfo=UTC),
        organization_ids=(OrganizationIdentity.source(digest),),
    )
    client = RecordingClient({"analytics:refusal-timeseries": []})
    repository = ClickHouseAnalyticsRepository(client)

    repository.refusal_timeseries(
        source_filter,
        QueryScope((), all_canonical=True, include_unmapped=True),
    )

    query, parameters = client.calls[0]
    assert digest not in query
    assert parameters["filter_source_digests"] == [digest]
    assert parameters["filter_identity_space"] == "IS_BG:REFUSALS:INCOMING"
    assert "SHA256" in query
