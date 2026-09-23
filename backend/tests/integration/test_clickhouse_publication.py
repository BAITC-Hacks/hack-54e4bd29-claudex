"""Opt-in isolated ClickHouse synthetic projection and daily/fact equality checks."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.repositories.clickhouse_analytics import ClickHouseAnalyticsRepository
from app.repositories.clickhouse_mapping import ClickHouseMappingRepository
from app.shared.analytics_contracts import AnalyticsFilter
from app.shared.analytics_data import QueryScope
from app.shared.mapping import MappingSnapshot

pytestmark = pytest.mark.skipif(
    not os.getenv("D_TEST_CLICKHOUSE_HOST"),
    reason="isolated D_TEST_CLICKHOUSE_HOST required; no application client fallback",
)


@pytest.fixture
def isolated_ch():
    import clickhouse_connect

    from data_pipeline.loading.clickhouse_migrations import apply_all

    assert os.getenv("D_TEST_ALLOW_ISOLATED") == "1"
    connection = {
        "host": os.environ["D_TEST_CLICKHOUSE_HOST"],
        "port": int(os.environ["D_TEST_CLICKHOUSE_PORT"]),
        "username": os.environ["D_TEST_CLICKHOUSE_USER"],
        "password": os.environ["D_TEST_CLICKHOUSE_PASSWORD"],
        "connect_timeout": 5,
        "send_receive_timeout": 10,
        "autogenerate_session_id": False,
    }
    admin = clickhouse_connect.get_client(**connection)
    database = "phase8-d-" + uuid4().hex
    admin.command(f"CREATE DATABASE `{database}`")
    client = clickhouse_connect.get_client(**connection, database=database)
    try:
        apply_all(
            client, Path(__file__).resolve().parents[3] / "database/clickhouse/migrations"
        )
        yield client
    finally:
        client.close()
        # Drop only this test's newly created UUID-named database.
        admin.command(f"DROP DATABASE `{database}`")
        admin.close()


def test_approved_projection_scope_publication_and_daily_equality(isolated_ch):
    client = isolated_ch
    hospital, other, published, partial = uuid4(), uuid4(), uuid4(), uuid4()
    day1 = datetime(2025, 1, 1, tzinfo=UTC)
    day2 = datetime(2025, 1, 2, tzinfo=UTC)
    rows = [
        ("synthetic-hmac-1", day1, "same-code", published, "ИС БГ", day2),
        ("synthetic-hmac-2", day2, "same-code", published, "ИС БГ", day2),
        ("synthetic-hmac-3", day2, "unmapped", published, "ИС БГ", day2),
        ("synthetic-hmac-4", day2, "same-code", partial, "ИС БГ", day2),
    ]
    client.insert(
        "fact_referral_events",
        rows,
        column_names=[
            "event_key",
            "registration_dt",
            "receiving_org_key",
            "import_id",
            "source_system",
            "ingested_at",
        ],
    )
    projection = ClickHouseMappingRepository(client)
    snapshot = MappingSnapshot.from_rows(
        "mapping-1",
        [
            ("ORGANIZATION", "IS_BG:REFERRALS:RECEIVING", "same-code", str(hospital)),
            ("ORGANIZATION", "IS_BG:WAITING:DESTINATION", "same-code", str(other)),
        ],
    )
    projection.publish(snapshot)
    projection.publish(snapshot)
    repository = ClickHouseAnalyticsRepository(client)
    filters = AnalyticsFilter(day1, datetime(2025, 1, 3, tzinfo=UTC))
    scope = QueryScope((hospital,), False, False, "mapping-1", (published,))
    daily = repository.referral_timeseries(filters, scope)
    assert (
        sum(p.value for p in daily)
        == repository.overview(filters, scope).referrals_total
        == 2
    )
    assert (
        repository.overview(
            filters, replace(scope, canonical_hospital_ids=(other,))
        ).referrals_total
        == 0
    )
    assert (
        repository.overview(
            filters, replace(scope, all_canonical=True, include_unmapped=True)
        ).referrals_total
        == 3
    )
    revoked = MappingSnapshot.from_rows(
        "mapping-2",
        [("ORGANIZATION", "IS_BG:WAITING:DESTINATION", "same-code", str(other))],
    )
    projection.publish(revoked)
    assert (
        repository.overview(
            filters, replace(scope, mapping_version="mapping-2")
        ).referrals_total
        == 0
    )
