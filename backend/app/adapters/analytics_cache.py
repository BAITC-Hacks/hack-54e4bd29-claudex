"""Redis cache adapter for low-cardinality analytics aggregates."""

from __future__ import annotations

import json
import uuid
from typing import Protocol

from app.shared.analytics_data import RawOrganization, RawOverview


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

    def get_organizations(
        self, key: str
    ) -> tuple[tuple[RawOrganization, ...], int] | None:
        payload = self._client.get(key)
        if payload is None:
            return None
        decoded = json.loads(payload)
        return (
            tuple(
                RawOrganization(
                    identity_space=item["identity_space"],
                    source_system=item["source_system"],
                    source_value=item["source_value"],
                    canonical_hospital_id=(
                        uuid.UUID(item["canonical_hospital_id"])
                        if item["canonical_hospital_id"] is not None
                        else None
                    ),
                    referrals_total=item["referrals_total"],
                    waiting_records=item["waiting_records"],
                    refusals_total=item["refusals_total"],
                    observed_waiting_median_days=item["observed_waiting_median_days"],
                )
                for item in decoded["rows"]
            ),
            int(decoded["total"]),
        )

    def set_organizations(
        self,
        key: str,
        value: tuple[tuple[RawOrganization, ...], int],
        ttl_seconds: int,
    ) -> None:
        rows, total = value
        payload = {
            "rows": [
                {
                    "identity_space": row.identity_space,
                    "source_system": row.source_system,
                    "source_value": row.source_value,
                    "canonical_hospital_id": (
                        str(row.canonical_hospital_id)
                        if row.canonical_hospital_id is not None
                        else None
                    ),
                    "referrals_total": row.referrals_total,
                    "waiting_records": row.waiting_records,
                    "refusals_total": row.refusals_total,
                    "observed_waiting_median_days": row.observed_waiting_median_days,
                }
                for row in rows
            ],
            "total": total,
        }
        self._client.setex(key, ttl_seconds, json.dumps(payload, separators=(",", ":")))
