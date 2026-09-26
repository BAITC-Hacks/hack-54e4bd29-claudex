"""Approve exact, invented fixture identities in an isolated local project only."""

from __future__ import annotations

import os

from app.business.mapping.service import MappingService
from app.composition import get_unit_of_work_factory
from app.core.config import AppEnv, get_settings
from app.database.clickhouse import get_client
from app.database.postgres import session_scope
from app.models.directory import Hospital, Region
from app.repositories.clickhouse_mapping import ClickHouseMappingRepository
from app.security.authorization import get_authorization_service
from app.security.context import DataScope, Role, SecurityContext

SPECS = (
    ("ORGANIZATION", "IS_BG:REFERRALS:RECEIVING", "synthetic-organization-a", "H-A1"),
    ("ORGANIZATION", "IS_BG:REFERRALS:RECEIVING", "synthetic-organization-b", "H-B1"),
    ("ORGANIZATION", "IS_BG:WAITING:DESTINATION", "SYN-A", "H-A1"),
    ("ORGANIZATION", "IS_BG:WAITING:DESTINATION", "SYN-B", "H-B1"),
    ("ORGANIZATION", "IS_BG:REFUSALS:INCOMING", "synthetic-organization-a", "H-A1"),
    ("ORGANIZATION", "IS_BG:REFUSALS:INCOMING", "synthetic-organization-b", "H-B1"),
    ("REGION", "IS_BG:WAITING:REGION", "01", "R-A"),
    ("REGION", "IS_BG:WAITING:REGION", "02", "R-B"),
    ("REGION", "IS_BG:REFUSALS:REGION", "SYNTHETIC-REGION-A", "R-A"),
    ("REGION", "IS_BG:REFUSALS:REGION", "SYNTHETIC-REGION-B", "R-B"),
)


def _guard() -> None:
    if (
        get_settings().app_env is not AppEnv.LOCAL
        or os.getenv("PHASE8_SYNTHETIC_ACCEPTANCE") != "1"
    ):
        raise RuntimeError("Synthetic acceptance mappings require explicit local opt-in")


def main() -> None:
    _guard()
    with session_scope() as session:
        regions = {row.code: row for row in session.query(Region).all()}
        hospitals = {row.code: row for row in session.query(Hospital).all()}
        if set(regions) != {"R-A", "R-B"} or set(hospitals) != {"H-A1", "H-A2", "H-B1"}:
            raise RuntimeError("Unexpected canonical directory in synthetic acceptance")
        if any(
            "[синтетические данные]" not in row.name
            for row in (*regions.values(), *hospitals.values())
        ):
            raise RuntimeError("Synthetic-only guard rejected canonical directory")
        targets = {
            **{k: v.id for k, v in regions.items()},
            **{k: v.id for k, v in hospitals.items()},
        }

    context = SecurityContext(
        user_id="phase8-synthetic-owner",
        roles=frozenset({Role.ADMIN}),
        scope=DataScope.global_scope(),
    )
    service = MappingService(
        get_unit_of_work_factory(),
        get_authorization_service(),
        ClickHouseMappingRepository(get_client()),
    )
    version = ""
    for kind, space, source_key, target_code in SPECS:
        alias_id = service.register(
            context,
            kind=kind,
            source_system="ИС БГ",
            identity_space=space,
            source_key=source_key,
        )
        decision = service.approve if kind == "ORGANIZATION" else service.approve_region
        version = decision(
            context, alias_id, targets[target_code], "phase8-synthetic-fixture-v1", 0
        )
    snapshot = service.publish(context, version)
    print(f"Synthetic exact mappings published: {len(SPECS)}, version={snapshot.version}")


if __name__ == "__main__":
    main()
