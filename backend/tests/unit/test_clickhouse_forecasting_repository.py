from __future__ import annotations

from datetime import date
from typing import ClassVar

from app.repositories.clickhouse_forecasting import ClickHouseReferralHistoryRepository


class Result:
    result_rows: ClassVar[list[tuple[date, int]]] = [
        (date(2025, 1, 1), 10),
        (date(2025, 1, 2), 12),
    ]


class Client:
    def __init__(self) -> None:
        self.query_text = ""

    def query(self, query: str, *, parameters=None):
        assert parameters in (None, {})
        self.query_text = query
        return Result()


def test_referral_history_is_daily_aggregate_without_event_rows() -> None:
    client = Client()
    repository = ClickHouseReferralHistoryRepository(client)

    result = repository.daily_global()

    assert [(item.observed_on, item.count) for item in result] == [
        (date(2025, 1, 1), 10),
        (date(2025, 1, 2), 12),
    ]
    assert "GROUP BY event_date" in client.query_text
    assert "event_key" not in client.query_text
    assert "LIMIT 400" in client.query_text
