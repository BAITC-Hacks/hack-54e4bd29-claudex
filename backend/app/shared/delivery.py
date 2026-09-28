"""Owner-reviewed delivery metadata; no source records or inferred completeness."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256
from uuid import UUID


class DeliveryMode(StrEnum):
    DELTA = "DELTA"
    SNAPSHOT = "SNAPSHOT"
    REPLACEMENT = "REPLACEMENT"


@dataclass(frozen=True)
class DeliveryManifest:
    delivery_id: str
    dataset_type: str
    source_system: str
    schema_version: str
    mode: DeliveryMode
    period_start: date | None
    period_end: date | None
    snapshot_date: date | None
    file_hashes: tuple[str, ...]
    expected_rows: int | None
    contract_version: str
    confirmed_complete_through: date | None = None

    def payload(self) -> dict:
        return json.loads(json.dumps(asdict(self), default=str))

    @property
    def digest(self) -> str:
        payload = self.payload()
        payload["file_hashes"] = sorted(self.file_hashes)
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @classmethod
    def from_payload(cls, payload: dict) -> DeliveryManifest:
        fields = dict(payload)
        for key in (
            "period_start",
            "period_end",
            "snapshot_date",
            "confirmed_complete_through",
        ):
            fields[key] = date.fromisoformat(fields[key]) if fields.get(key) else None
        fields["mode"] = DeliveryMode(fields["mode"])
        fields["file_hashes"] = tuple(fields["file_hashes"])
        return cls(**fields)


@dataclass(frozen=True)
class DeliveryReadiness:
    dataset_type: str
    published_import_ids: tuple[UUID, ...] = ()
    confirmed_complete_through: date | None = None
    publication_watermark: str = ""
    completeness: str = "UNKNOWN"
    cadence_days: int | None = None
    snapshot_semantics_approved: bool = False
    reason: str | None = "CONTRACT_NOT_APPROVED"
    snapshot_approved_import_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class DeliveryEvidence:
    rows: int
    event_period_start: date | None
    event_period_end: date | None
    snapshot_date: date | None
