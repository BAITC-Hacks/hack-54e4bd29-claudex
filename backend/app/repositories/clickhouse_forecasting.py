"""Bounded ClickHouse reads used to build the forecasting dataset."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Protocol
from uuid import UUID

from app.shared.forecasting import DailyReferralCount


class QueryResult(Protocol):
    result_rows: list[tuple[date, int]]


class ClickHouseQueryClient(Protocol):
    def query(
        self, query: str, *, parameters: dict[str, object] | None = None
    ) -> QueryResult: ...


class ClickHouseReferralHistoryRepository:
    def __init__(
        self,
        client: ClickHouseQueryClient,
        *,
        import_ids_provider: Callable[[], tuple[UUID, ...]] | None = None,
    ) -> None:
        self._client = client
        self._import_ids_provider = import_ids_provider

    def daily_global(self) -> tuple[DailyReferralCount, ...]:
        if self._import_ids_provider is None:
            raise ValueError("PUBLICATION_ALLOWLIST_REQUIRED")
        import_ids = self._import_ids_provider()
        if not import_ids:
            return ()
        rows = self._client.query(
            """
            /* forecasting:referrals-daily-global */
            SELECT toDate(registration_dt) AS event_date, count() AS referrals
            FROM fact_referral_events
            WHERE import_id IN {published_import_ids:Array(UUID)}
            GROUP BY event_date
            ORDER BY event_date
            LIMIT 400
            """,
            parameters={"published_import_ids": [str(item) for item in import_ids]},
        ).result_rows
        return tuple(DailyReferralCount(row[0], int(row[1])) for row in rows)
