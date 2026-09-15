"""Redis cache adapter for low-cardinality analytics aggregates."""

from __future__ import annotations

import json
from typing import Protocol

from app.shared.analytics_data import RawOverview


class RedisLike(Protocol):
    def get(self, name: str) -> str | None: ...

    def setex(self, name: str, time: int, value: str) -> object: ...


class RedisAnalyticsCache:
    def __init__(self, client: RedisLike) -> None:
        self._client = client

    def get_overview(self, key: str) -> RawOverview | None:
        payload = self._client.get(key)
        if payload is None:
            return None
        decoded = json.loads(payload)
        return RawOverview(**decoded)

    def set_overview(self, key: str, value: RawOverview, ttl_seconds: int) -> None:
        payload = {
            "referrals_total": value.referrals_total,
            "waiting_records": value.waiting_records,
            "refusals_total": value.refusals_total,
            "hospitalized_total": value.hospitalized_total,
            "unknown_records": value.unknown_records,
            "represented_organizations": value.represented_organizations,
            "represented_regions": value.represented_regions,
        }
        self._client.setex(key, ttl_seconds, json.dumps(payload, separators=(",", ":")))
