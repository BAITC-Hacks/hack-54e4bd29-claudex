"""Exact source identities and immutable, verified mapping snapshots."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID

ORGANIZATION_SPACES = frozenset(
    {
        "IS_BG:REFERRALS:RECEIVING",
        "IS_BG:REFERRALS:REFERRING",
        "IS_BG:WAITING:DESTINATION",
        "IS_BG:REFUSALS:INCOMING",
        "ERSB:TREATED:ORGANIZATION",
    }
)
REGION_SPACES = frozenset(
    {
        "IS_BG:REFERRALS:REGION",
        "IS_BG:WAITING:REGION",
        "IS_BG:REFUSALS:REGION",
        "ERSB:TREATED:REGION",
    }
)


@dataclass(frozen=True)
class ApprovedOrganizationMapping:
    identity_space: str
    source_key: str
    hospital_id: UUID


@dataclass(frozen=True)
class ApprovedRegionMapping:
    identity_space: str
    source_key: str
    region_id: UUID


@dataclass(frozen=True)
class MappingReadiness:
    version: str | None = None
    generation: int = 0
    verified: bool = False


@dataclass(frozen=True)
class MappingReviewItem:
    """Bounded operator-only review row; no patient or clinical fields."""

    alias_id: UUID
    kind: str
    source_system: str
    identity_space: str | None
    source_identifier: str
    occurrences: int
    mapping_status: str
    mapping_method: str | None
    canonical_id: UUID | None
    alias_version: int | None
    approved_mapping_version: str | None
    approved_by: str | None
    approved_at: datetime | None
    evidence_ref: str | None


@dataclass(frozen=True)
class MappingSnapshot:
    version: str
    organizations: tuple[ApprovedOrganizationMapping, ...]
    digest: str
    regions: tuple[ApprovedRegionMapping, ...] = ()

    def rows(self) -> tuple[tuple[str, str, str, str], ...]:
        return tuple(
            sorted(
                [
                    ("ORGANIZATION", m.identity_space, m.source_key, str(m.hospital_id))
                    for m in self.organizations
                ]
                + [
                    ("REGION", m.identity_space, m.source_key, str(m.region_id))
                    for m in self.regions
                ]
            )
        )

    @classmethod
    def from_rows(
        cls, version: str, rows: Iterable[tuple[str, str, str, str]]
    ) -> MappingSnapshot:
        rows = tuple(
            sorted((kind, space, key, target) for kind, space, key, target in rows)
        )
        keys = [(r[0], r[1], r[2]) for r in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("DUPLICATE_MAPPING_IDENTITY")
        for kind, space, key, target in rows:
            allowed = (
                ORGANIZATION_SPACES
                if kind == "ORGANIZATION"
                else REGION_SPACES
                if kind == "REGION"
                else ()
            )
            if space not in allowed or not key or not target:
                raise ValueError("INVALID_MAPPING_IDENTITY")
        digest = sha256(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(
            version,
            tuple(
                ApprovedOrganizationMapping(space, key, UUID(target))
                for kind, space, key, target in rows
                if kind == "ORGANIZATION"
            ),
            digest,
            tuple(
                ApprovedRegionMapping(space, key, UUID(target))
                for kind, space, key, target in rows
                if kind == "REGION"
            ),
        )
