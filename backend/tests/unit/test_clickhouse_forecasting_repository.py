from __future__ import annotations

from datetime import date
from typing import ClassVar
from uuid import UUID

import pytest

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
        assert parameters == {"published_import_ids": [str(UUID(int=1))]}
        self.query_text = query
        return Result()


def test_referral_history_is_daily_aggregate_without_event_rows() -> None:
    client = Client()
    repository = ClickHouseReferralHistoryRepository(
        client, import_ids_provider=lambda: (UUID(int=1),)
    )

    result = repository.daily_global()

    assert [(item.observed_on, item.count) for item in result] == [
        (date(2025, 1, 1), 10),
        (date(2025, 1, 2), 12),
    ]
    assert "GROUP BY event_date" in client.query_text
    assert "event_key" not in client.query_text
    assert "LIMIT 400" in client.query_text


def test_global_history_cannot_read_unpublished_rows_without_trusted_allowlist():
    class ForbiddenClient:
        def query(self, *_args, **_kwargs):
            raise AssertionError("Unfiltered ClickHouse read")

    with pytest.raises(ValueError, match="PUBLICATION_ALLOWLIST_REQUIRED"):
        ClickHouseReferralHistoryRepository(ForbiddenClient()).daily_global()


def test_global_history_empty_publication_set_returns_no_history():
    class ForbiddenClient:
        def query(self, *_args, **_kwargs):
            raise AssertionError("No imports were approved")

    assert (
        ClickHouseReferralHistoryRepository(
            ForbiddenClient(), import_ids_provider=lambda: ()
        ).daily_global()
        == ()
    )


def test_global_history_binds_publication_ids_in_sql():
    client = Client()
    ClickHouseReferralHistoryRepository(
        client, import_ids_provider=lambda: (UUID(int=1),)
    ).daily_global()
    assert "import_id IN {published_import_ids:Array(UUID)}" in client.query_text
