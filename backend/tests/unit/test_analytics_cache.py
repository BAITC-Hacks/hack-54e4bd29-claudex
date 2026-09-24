"""Redis analytics cache serializes bounded aggregate pages without identity loss."""

from __future__ import annotations

import uuid

from app.adapters.analytics_cache import RedisAnalyticsCache
from app.shared.analytics_data import RawOrganization


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def setex(self, name: str, time: int, value: str) -> None:
        self.values[name] = value
        self.ttls[name] = time


def test_organization_page_round_trips_canonical_and_unmapped_rows() -> None:
    redis = FakeRedis()
    cache = RedisAnalyticsCache(redis)
    rows = (
        RawOrganization(
            "IS_BG:REFERRALS:RECEIVING",
            "ИС БГ",
            "synthetic-org-a",
            uuid.uuid4(),
            17,
            0,
            0,
            4.5,
        ),
        RawOrganization(
            "IS_BG:WAITING:DESTINATION",
            "ИС БГ",
            "synthetic-org-b",
            None,
            0,
            12,
            0,
            None,
        ),
    )

    assert cache.get_organizations("scope-safe-key") is None
    cache.set_organizations("scope-safe-key", (rows, 200), 60)

    assert cache.get_organizations("scope-safe-key") == (rows, 200)
    assert redis.ttls["scope-safe-key"] == 60
