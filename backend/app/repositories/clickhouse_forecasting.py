"""Bounded ClickHouse reads used to build the forecasting dataset."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.shared.forecasting import DailyReferralCount


class QueryResult(Protocol):
    result_rows: list[tuple[date, int]]


class ClickHouseQueryClient(Protocol):
    def query(
        self, query: str, *, parameters: dict[str, object] | None = None
    ) -> QueryResult: ...


class ClickHouseReferralHistoryRepository:
    def __init__(self, client: ClickHouseQueryClient) -> None:
        self._client = client

    def daily_global(self) -> tuple[DailyReferralCount, ...]:
        rows = self._client.query(
            """
            /* forecasting:referrals-daily-global */
            SELECT toDate(registration_dt) AS event_date, count() AS referrals
            FROM fact_referral_events
            GROUP BY event_date
            ORDER BY event_date
            LIMIT 400
            """,
            parameters={},
        ).result_rows
        return tuple(DailyReferralCount(row[0], int(row[1])) for row in rows)
