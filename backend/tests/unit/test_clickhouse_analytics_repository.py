"""ClickHouse analytics repository returns aggregates and parameterizes input."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from prometheus_client import REGISTRY

from app.business.analytics.contracts import (
    AnalyticsFilter,
    Granularity,
    OrganizationIdentity,
)
from app.business.analytics.ports import QueryScope
from app.core.analytics_metrics import clickhouse_query_duration_seconds
from app.repositories.clickhouse_analytics import ClickHouseAnalyticsRepository
from app.shared.organization_ref import source_organization_digest


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


def test_clickhouse_query_duration_records_only_bounded_operation_label() -> None:
    client = RecordingClient({"analytics:referral-timeseries": []})
    repository = ClickHouseAnalyticsRepository(client)
    clickhouse_query_duration_seconds.labels(operation="fact_read")
    before = (
        REGISTRY.get_sample_value(
            "medsignal_clickhouse_query_duration_seconds_count",
            {"operation": "fact_read"},
        )
        or 0
    )

    repository.referral_timeseries(
        filters(), QueryScope((), all_canonical=True, include_unmapped=True)
    )

    assert (
        REGISTRY.get_sample_value(
            "medsignal_clickhouse_query_duration_seconds_count",
            {"operation": "fact_read"},
        )
        == before + 1
    )


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
        {
            "analytics:latest-waiting-snapshot": [(snapshot,)],
            "analytics:waiting-summary": [(100, 2, 10.5, 20.5, 30.5, 90.0)],
        }
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
    assert all(
        "f.import_id IN {waiting_import_ids:Array(UUID)}" in query
        for query, _ in client.calls
    )
    assert "snapshot_dt = {selected_snapshot:DateTime64(3)}" in client.calls[1][0]
    assert client.calls[1][1]["selected_snapshot"] == snapshot


def test_empty_waiting_summary_converts_nan_and_epoch_sentinel_to_none() -> None:
    client = RecordingClient(
        {
            "analytics:latest-waiting-snapshot": [(None,)],
            "analytics:waiting-summary": [
                (0, 0, float("nan"), float("nan"), float("nan"), 0.0)
            ],
        }
    )
    repository = ClickHouseAnalyticsRepository(client)

    result = repository.waiting_summary(
        filters(), QueryScope((), all_canonical=True, include_unmapped=True)
    )

    assert result.snapshot_dt is None
    assert result.waiting_records == 0
    assert result.median_days is None
    assert result.p75_days is None
    assert result.p90_days is None
    assert result.oldest_days is None
    assert len(client.calls) == 1


def test_selected_snapshot_date_survives_empty_registration_cohort() -> None:
    snapshot = datetime(2025, 3, 1, tzinfo=UTC)
    client = RecordingClient(
        {
            "analytics:latest-waiting-snapshot": [(snapshot,)],
            "analytics:waiting-summary": [
                (0, 0, float("nan"), float("nan"), float("nan"), 0.0)
            ],
        }
    )
    repository = ClickHouseAnalyticsRepository(client)

    result = repository.waiting_summary(
        filters(profile="a-profile-absent-in-current-snapshot"),
        QueryScope((), all_canonical=True, include_unmapped=True),
    )

    assert result.snapshot_dt == snapshot
    assert result.waiting_records == 0
    assert result.median_days is None
    selection_query, _ = client.calls[0]
    assert "registration_dt >= " not in selection_query
    assert "profile_source = " not in selection_query


def test_waiting_snapshot_selection_is_shared_by_overview_and_organizations() -> None:
    snapshot = datetime(2026, 5, 13, tzinfo=UTC)
    reviewed = uuid.uuid4()
    client = RecordingClient(
        {
            "analytics:latest-waiting-snapshot": [(snapshot,)],
            "analytics:overview-referrals": [(7, 0, 0, 1)],
            "analytics:overview-waiting": [(3, 1, 1)],
            "analytics:overview-refusals": [(2, 1, 1)],
            "analytics:organizations": [],
        }
    )
    repository = ClickHouseAnalyticsRepository(client)
    scope = QueryScope(
        (), True, True, "mapping-1", (reviewed,), waiting_import_ids=(reviewed,)
    )

    overview = repository.overview(filters(), scope)
    repository.organizations(filters(), scope, limit=20, offset=0)

    assert overview.waiting_records == 3
    waiting_queries = [
        (query, params)
        for query, params in client.calls
        if "analytics:overview-waiting" in query or "analytics:organizations" in query
    ]
    assert len(waiting_queries) == 2
    assert all(
        "snapshot_dt = {selected_snapshot:DateTime64(3)}" in query
        and params["selected_snapshot"] == snapshot
        and params["waiting_import_ids"] == [str(reviewed)]
        for query, params in waiting_queries
    )


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


def test_empty_observed_waiting_converts_non_finite_aggregates_to_none() -> None:
    client = RecordingClient(
        {
            "analytics:observed-waiting": [
                (0, 0, 0.0, float("nan"), float("inf"), float("-inf"))
            ]
        }
    )
    repository = ClickHouseAnalyticsRepository(client)

    result = repository.observed_waiting(
        filters(), QueryScope((), all_canonical=True, include_unmapped=True)
    )

    assert result.mean_days is None
    assert result.median_days is None
    assert result.p75_days is None
    assert result.p90_days is None


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


def test_organization_list_converts_nan_waiting_median_to_none() -> None:
    client = RecordingClient(
        {
            "analytics:organizations": [
                (
                    "IS_BG:REFERRALS:RECEIVING",
                    "IS_BG",
                    "safe-source-key",
                    None,
                    3,
                    0,
                    0,
                    float("nan"),
                    1,
                )
            ]
        }
    )
    repository = ClickHouseAnalyticsRepository(client)

    organizations, total = repository.organizations(
        filters(),
        QueryScope((), all_canonical=True, include_unmapped=True),
        limit=20,
        offset=0,
    )

    assert total == 1
    assert organizations[0].observed_waiting_median_days is None


def test_source_organization_detail_filters_digest_in_clickhouse() -> None:
    source_value = "source-org-17"
    digest = source_organization_digest("IS_BG:WAITING:DESTINATION", source_value)
    client = RecordingClient(
        {
            "analytics:organizations": [
                (
                    "IS_BG:WAITING:DESTINATION",
                    "IS_BG",
                    source_value,
                    None,
                    0,
                    12,
                    0,
                    None,
                    1,
                )
            ]
        }
    )
    repository = ClickHouseAnalyticsRepository(client)

    result = repository.organization_detail(
        f"source:{digest}",
        filters(),
        QueryScope((), all_canonical=True, include_unmapped=True),
    )

    assert result is not None
    assert result[0].source_value == source_value
    assert len(client.calls) == 2
    query, parameters = client.calls[1]
    assert "SHA256" in query
    assert source_value not in query
    assert parameters["waiting_filter_source_digests"] == [digest]
    assert parameters["limit"] == 1
    assert parameters["offset"] == 0


def test_organizations_aggregate_by_source_before_mapping_and_filter_publication() -> (
    None
):
    client = RecordingClient({"analytics:organizations": []})
    repository = ClickHouseAnalyticsRepository(client)
    published_id = uuid.uuid4()

    repository.organizations(
        filters(),
        QueryScope(
            (),
            all_canonical=True,
            include_unmapped=True,
            mapping_version="mapping-42",
            published_import_ids=(published_id,),
        ),
        limit=20,
        offset=0,
    )

    query, parameters = client.calls[1]
    assert "FROM fact_referral_events AS f" in query
    assert "FROM fact_waiting_events AS f" in query
    assert "FROM fact_refusal_events AS f" in query
    assert "GROUP BY source_system, receiving_org_key" in query
    assert "LEFT JOIN" in query
    assert "f.import_id IN {published_import_ids:Array(UUID)}" in query
    assert "f.import_id IN {waiting_import_ids:Array(UUID)}" in query
    assert parameters["published_import_ids"] == [str(published_id)]
    assert parameters["mapping_version"] == "mapping-42"
