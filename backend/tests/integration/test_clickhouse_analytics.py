"""Real ClickHouse aggregate reconciliation for Phase 4."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from app.business.analytics.contracts import AnalyticsFilter, Granularity
from app.database.clickhouse import get_client
from app.repositories.clickhouse_analytics import ClickHouseAnalyticsRepository
from app.shared.analytics_data import QueryScope

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_CLICKHOUSE_INTEGRATION") != "1",
    reason="requires the local ClickHouse with imported Phase 3B facts",
)


def test_daily_aggregates_reconcile_to_fact_counts() -> None:
    repository = ClickHouseAnalyticsRepository(get_client())
    filters = AnalyticsFilter(
        date_from=datetime(2025, 1, 1, tzinfo=UTC),
        date_to=datetime(2025, 3, 31, 23, 59, 59, 999000, tzinfo=UTC),
        granularity=Granularity.DAY,
    )
    scope = QueryScope((), all_canonical=True, include_unmapped=True)

    overview = repository.overview(filters, scope)
    referrals = repository.referral_timeseries(filters, scope)
    refusals = repository.refusal_timeseries(filters, scope)

    assert sum(item.value for item in referrals) == overview.referrals_total == 767_130
    assert sum(item.value for item in refusals) == overview.refusals_total == 1_508_732
    assert len(referrals) == 90
    assert len(refusals) == 90


def test_waiting_and_observed_waiting_semantics_match_loaded_facts() -> None:
    repository = ClickHouseAnalyticsRepository(get_client())
    filters = AnalyticsFilter(
        date_from=datetime(2025, 1, 1, tzinfo=UTC),
        date_to=datetime(2025, 3, 31, 23, 59, 59, 999000, tzinfo=UTC),
    )
    scope = QueryScope((), all_canonical=True, include_unmapped=True)

    waiting = repository.waiting_summary(filters, scope)
    observed = repository.observed_waiting(filters, scope)

    assert waiting.waiting_records == 765_182
    assert waiting.snapshot_dt is not None
    assert observed.observed_records == 574_444
    assert observed.excluded_chronology_conflicts == 104_644
