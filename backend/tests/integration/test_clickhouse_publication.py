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
from app.shared.organization_ref import source_organization_digest

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
        assert client.query("SELECT currentDatabase()").result_rows[0][0] == database
        assert ("fact_referral_events",) in client.query("SHOW TABLES").result_rows
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
    client.insert(
        "fact_waiting_events",
        [("synthetic-patient-key", day2, day2, "same-code", published, "ИС БГ", day2)],
        column_names=[
            "patient_key",
            "registration_dt",
            "snapshot_dt",
            "hospital_source",
            "import_id",
            "source_system",
            "ingested_at",
        ],
    )
    client.insert(
        "fact_refusal_events",
        [(day2, "same-code", published, "ИС БГ", day2)],
        column_names=[
            "refuse_dt",
            "hospital_source",
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
            ("ORGANIZATION", "IS_BG:REFUSALS:INCOMING", "same-code", str(hospital)),
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
    mapped_rows, mapped_total = repository.organizations(
        filters, scope, limit=20, offset=0
    )
    assert mapped_total == 2
    assert sum(row.referrals_total for row in mapped_rows) == 2
    assert sum(row.refusals_total for row in mapped_rows) == 1
    assert sum(row.waiting_records for row in mapped_rows) == 0
    global_scope = replace(scope, all_canonical=True, include_unmapped=True)
    global_rows, global_total = repository.organizations(
        filters, global_scope, limit=20, offset=0
    )
    assert global_total == 4
    assert sum(row.referrals_total for row in global_rows) == 3
    assert sum(row.waiting_records for row in global_rows) == 1
    assert sum(row.refusals_total for row in global_rows) == 1
    source_ref = "source:" + source_organization_digest(
        "IS_BG:REFERRALS:RECEIVING", "unmapped"
    )
    source_result = repository.organization_detail(source_ref, filters, global_scope)
    assert source_result is not None
    assert source_result[0].referrals_total == 1
    assert repository.organization_detail(source_ref, filters, scope) is None
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
    revoked_rows, revoked_total = repository.organizations(
        filters, replace(scope, mapping_version="mapping-2"), limit=20, offset=0
    )
    assert revoked_rows == ()
    assert revoked_total == 0


def test_failed_import_rows_are_invisible_before_clickhouse_cleanup(isolated_ch):
    client = isolated_ch
    published, failed = uuid4(), uuid4()
    day = datetime(2025, 1, 1, tzinfo=UTC)
    client.insert(
        "fact_referral_events",
        [
            ("synthetic-published", day, "published-org", published, "ИС БГ", day),
            ("synthetic-failed", day, "failed-org", failed, "ИС БГ", day),
        ],
        column_names=[
            "event_key",
            "registration_dt",
            "receiving_org_key",
            "import_id",
            "source_system",
            "ingested_at",
        ],
    )
    assert client.query("SELECT count() FROM fact_referral_events").result_rows == [(2,)]
    scope = QueryScope((), True, True, "mapping-1", (published,))
    filters = AnalyticsFilter(day, datetime(2025, 1, 2, tzinfo=UTC))
    repository = ClickHouseAnalyticsRepository(client)

    assert repository.overview(filters, scope).referrals_total == 1
    assert sum(p.value for p in repository.referral_timeseries(filters, scope)) == 1
    rows, total = repository.organizations(filters, scope, limit=20, offset=0)
    assert total == 1
    assert rows[0].source_value == "published-org"

    # A failed import remains physically present while an asynchronous DELETE
    # may still be running. Revoking publication blocks it immediately.
    revoked = replace(scope, published_import_ids=())
    assert repository.overview(filters, revoked).referrals_total == 0
    revoked_rows, revoked_total = repository.organizations(
        filters, revoked, limit=20, offset=0
    )
    assert revoked_rows == ()
    assert revoked_total == 0


def test_waiting_endpoints_select_one_published_snapshot_per_scope(isolated_ch):
    """Synthetic old/new/unpublished exports must not be added as one queue."""
    client = isolated_ch
    hospital, other_hospital, old_import, new_import, other_import, unpublished = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    registration = datetime(2025, 1, 1, tzinfo=UTC)
    new_registration = datetime(2025, 1, 2, tzinfo=UTC)
    old_snapshot = datetime(2025, 1, 3, tzinfo=UTC)
    new_snapshot = datetime(2025, 1, 4, tzinfo=UTC)
    hidden_snapshot = datetime(2025, 1, 5, tzinfo=UTC)
    newer_other_snapshot = datetime(2025, 1, 5, tzinfo=UTC)
    client.insert(
        "fact_waiting_events",
        [
            (
                "synthetic-1",
                registration,
                old_snapshot,
                "org-a",
                old_import,
                "ИС БГ",
                old_snapshot,
            ),
            (
                "synthetic-2",
                new_registration,
                new_snapshot,
                "org-a",
                new_import,
                "ИС БГ",
                new_snapshot,
            ),
            (
                "synthetic-3",
                new_registration,
                new_snapshot,
                "org-a",
                new_import,
                "ИС БГ",
                new_snapshot,
            ),
            (
                "synthetic-4",
                registration,
                hidden_snapshot,
                "org-a",
                unpublished,
                "ИС БГ",
                hidden_snapshot,
            ),
            (
                "synthetic-5",
                registration,
                newer_other_snapshot,
                "org-b",
                other_import,
                "ИС БГ",
                newer_other_snapshot,
            ),
        ],
        column_names=[
            "patient_key",
            "registration_dt",
            "snapshot_dt",
            "hospital_source",
            "import_id",
            "source_system",
            "ingested_at",
        ],
    )
    projection = ClickHouseMappingRepository(client)
    projection.publish(
        MappingSnapshot.from_rows(
            "mapping-waiting",
            [
                ("ORGANIZATION", "IS_BG:WAITING:DESTINATION", "org-a", str(hospital)),
                (
                    "ORGANIZATION",
                    "IS_BG:WAITING:DESTINATION",
                    "org-b",
                    str(other_hospital),
                ),
            ],
        )
    )
    repository = ClickHouseAnalyticsRepository(client)
    filters = AnalyticsFilter(registration, datetime(2025, 1, 6, tzinfo=UTC))
    scope = QueryScope(
        (hospital,),
        False,
        False,
        "mapping-waiting",
        (old_import, new_import, other_import),
        (old_import, new_import, other_import, unpublished),
    )

    summary = repository.waiting_summary(filters, scope)
    overview = repository.overview(filters, scope)
    organizations, _ = repository.organizations(filters, scope, limit=20, offset=0)

    # DateTime64 without an explicit timezone preserves the source clock time.
    assert summary.snapshot_dt == new_snapshot.replace(tzinfo=None)
    assert summary.waiting_records == overview.waiting_records == 2
    assert sum(item.waiting_records for item in organizations) == 2
    old_cohort = AnalyticsFilter(registration, registration)
    old_cohort_summary = repository.waiting_summary(old_cohort, scope)
    assert old_cohort_summary.snapshot_dt == new_snapshot.replace(tzinfo=None)
    assert old_cohort_summary.waiting_records == 0
    assert repository.overview(old_cohort, scope).waiting_records == 0
    global_scope = replace(scope, all_canonical=True, include_unmapped=True)
    assert repository.waiting_summary(filters, global_scope).snapshot_dt == (
        newer_other_snapshot.replace(tzinfo=None)
    )
    assert repository.overview(filters, global_scope).waiting_records == 1
    assert repository.waiting_summary(
        filters, replace(scope, waiting_import_ids=(old_import,))
    ).snapshot_dt == old_snapshot.replace(tzinfo=None)
    assert (
        repository.overview(
            filters, replace(scope, waiting_import_ids=())
        ).waiting_records
        == 0
    )
