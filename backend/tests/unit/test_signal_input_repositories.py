from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.repositories.signal_inputs import SqlClickHouseSignalInputRepository


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
            return Result([(date(2025, 3, 29), 10), (date(2025, 3, 30), 12)])
        if "signal-engine:latest:REFERRALS" in query:
            return Result([(datetime(2025, 3, 31, 23, tzinfo=UTC),)])
        raise AssertionError(query)


def test_daily_evidence_uses_bounded_aggregate_and_excludes_partial_day() -> None:
    client = Client()
    repository = SqlClickHouseSignalInputRepository(client, session_factory=None)

    result = repository.daily_evidence(
        "REFERRALS",
        before=date(2025, 3, 31),
        source_is_current=True,
        limit_days=63,
    )

    assert [(point.observed_on, point.value) for point in result.points] == [
        (date(2025, 3, 29), 10),
        (date(2025, 3, 30), 12),
    ]
    assert "GROUP BY event_date" in client.query_text
    assert "registration_dt" in client.query_text
    assert "< {before:Date}" in client.query_text
    assert "event_key" not in client.query_text
    assert client.parameters == {"before": date(2025, 3, 31), "limit_days": 63}


def test_latest_event_timestamp_uses_allowlisted_column() -> None:
    client = Client()
    repository = SqlClickHouseSignalInputRepository(client, session_factory=None)

    result = repository.latest_event_at("REFERRALS")

    assert result == datetime(2025, 3, 31, 23, tzinfo=UTC)
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
