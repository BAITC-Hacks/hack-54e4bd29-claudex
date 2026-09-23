from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.repositories.signal_inputs import SqlClickHouseSignalInputRepository
from tests.unit import test_organization_forecast_repository as sql_fixtures

seed_publication = sql_fixtures.seed_publication
sessions = sql_fixtures.sessions


class Result:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.result_rows = rows


class Client:
    def __init__(self) -> None:
        self.query_text = ""
        self.parameters: dict[str, object] = {}

    def query(self, query: str, *, parameters=None):
        self.query_text = query
        self.parameters = parameters or {}
        if "signal-engine:daily:REFERRALS" in query:
            return Result([(date(2026, 9, 21), 10), (date(2026, 9, 22), 12)])
        if "signal-engine:latest:REFERRALS" in query:
            return Result([(datetime(2026, 9, 22, 23, tzinfo=UTC),)])
        raise AssertionError(query)


def test_daily_evidence_uses_bounded_aggregate_and_excludes_partial_day(sessions) -> None:
    delivery = seed_publication(sessions)
    client = Client()
    repository = SqlClickHouseSignalInputRepository(client, session_factory=sessions)

    result = repository.daily_evidence(
        "REFERRALS",
        before=date(2026, 9, 23),
        source_is_current=True,
        limit_days=63,
    )

    assert [(point.observed_on, point.value) for point in result.points] == [
        (date(2026, 9, 21), 10),
        (date(2026, 9, 22), 12),
    ]
    assert "GROUP BY event_date" in client.query_text
    assert "registration_dt" in client.query_text
    assert "< {before:Date}" in client.query_text
    assert "event_key" not in client.query_text
    assert client.parameters["before"] == date(2026, 9, 23)
    assert client.parameters["limit_days"] == 63
    assert client.parameters["published_import_ids"] == [
        str(i) for i in delivery.published_import_ids
    ]
    assert "import_id IN {published_import_ids:Array(UUID)}" in client.query_text
    assert all(point.is_complete for point in result.points)


def test_latest_event_timestamp_uses_allowlisted_column(sessions) -> None:
    seed_publication(sessions)
    client = Client()
    repository = SqlClickHouseSignalInputRepository(client, session_factory=sessions)

    result = repository.latest_event_at("REFERRALS")

    assert result == datetime(2026, 9, 22, 23, tzinfo=UTC)
    assert "max(registration_dt)" in client.query_text


def test_unknown_dataset_cannot_be_interpolated_into_clickhouse_sql() -> None:
    repository = SqlClickHouseSignalInputRepository(Client(), session_factory=None)

    with pytest.raises(ValueError, match="не поддерживается"):
        repository.daily_evidence(
            "REFERRALS; DROP TABLE facts",
            before=date(2025, 4, 1),
            source_is_current=True,
            limit_days=63,
        )


def test_unknown_delivery_coverage_cannot_become_complete_spike_input():
    client = Client()
    result = SqlClickHouseSignalInputRepository(client, None).daily_evidence(
        "REFERRALS", before=date(2026, 9, 23), source_is_current=True, limit_days=63
    )
    assert not result.points and not result.source_is_current
    assert client.query_text == ""


def test_partial_delivery_prevents_daily_operational_input(sessions):
    from sqlalchemy import select

    from app.models.delivery import Delivery

    seed_publication(sessions)
    with sessions.begin() as session:
        session.scalar(select(Delivery)).status = "APPROVED"
    client = Client()
    result = SqlClickHouseSignalInputRepository(client, sessions).daily_evidence(
        "REFERRALS", before=date(2026, 9, 23), source_is_current=True, limit_days=63
    )
    assert not result.points and not result.source_is_current
    assert client.query_text == ""


def test_completed_import_in_unpublished_delivery_is_not_freshness_evidence(sessions):
    from sqlalchemy import select

    from app.models.delivery import Delivery

    seed_publication(sessions)
    with sessions.begin() as session:
        session.scalar(select(Delivery)).status = "APPROVED"
    repository = SqlClickHouseSignalInputRepository(Client(), sessions)
    assert repository._completed_imports() == []
    assert repository.latest_event_at("REFERRALS") is None
