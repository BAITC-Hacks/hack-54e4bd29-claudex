"""Publish exact invented source mappings only in an opted-in local demo."""

from __future__ import annotations

import os

from app.business.mapping.service import MappingService
from app.composition import get_unit_of_work_factory
from app.core.config import get_settings
from app.database.clickhouse import get_client
from app.database.postgres import session_scope
from app.models.directory import Hospital, Region
from app.repositories.clickhouse_mapping import ClickHouseMappingRepository
from app.security.authorization import get_authorization_service
from app.security.context import DataScope, Role, SecurityContext
from seeds.dev_seed import SYNTHETIC_MARK
from seeds.local_demo_seed import load_profile, require_local_demo

MappingSpec = tuple[str, str, str, str]


def mapping_specs(profile: tuple[dict[str, str], ...]) -> tuple[MappingSpec, ...]:
    """Return the five audited identity spaces for every fictional region."""
    specs: list[MappingSpec] = []
    for item in profile:
        code = item["code"]
        specs.extend(
            (
                (
                    "ORGANIZATION",
                    "IS_BG:REFERRALS:RECEIVING",
                    f"SYN-ORG-{code}".lower(),
                    f"H-{code}",
                ),
                (
                    "ORGANIZATION",
                    "IS_BG:WAITING:DESTINATION",
                    f"SYN-WAIT-{code}",
                    f"H-{code}",
                ),
                (
                    "ORGANIZATION",
                    "IS_BG:REFUSALS:INCOMING",
                    f"SYN-ORG-{code}".lower(),
                    f"H-{code}",
                ),
                ("REGION", "IS_BG:WAITING:REGION", f"SYN-REG-{code}", code),
                ("REGION", "IS_BG:REFUSALS:REGION", f"SYN-REF-REG-{code}", code),
            )
        )
    unique_aliases = {(kind, space, key) for kind, space, key, _ in specs}
    if len(specs) != 60 or len(unique_aliases) != 60:
        raise RuntimeError("Local demo source aliases are incomplete or duplicated")
    return tuple(specs)


def validate_directory(
    profile: tuple[dict[str, str], ...],
    region_codes: set[str],
    hospital_codes: set[str],
) -> None:
    """Reject an existing or mixed canonical directory before any decision."""
    expected_regions = {item["code"] for item in profile}
    expected_hospitals = {f"H-{code}" for code in expected_regions}
    if region_codes != expected_regions or hospital_codes != expected_hospitals:
        raise RuntimeError("Unexpected canonical directory in local synthetic demo")


def publish() -> str:
    """Approve all source identities, then publish one exact mapping snapshot."""
    require_local_demo(get_settings().app_env, os.getenv("LOCAL_SYNTHETIC_DEMO"))
    profile = load_profile()
    specs = mapping_specs(profile)
    with session_scope() as session:
        regions = {row.code: row for row in session.query(Region).all()}
        hospitals = {row.code: row for row in session.query(Hospital).all()}
        validate_directory(profile, set(regions), set(hospitals))
        if any(
            SYNTHETIC_MARK not in row.name
            for row in (*regions.values(), *hospitals.values())
        ):
            raise RuntimeError("Local demo canonical directory lacks synthetic marks")
        targets = {
            **{code: row.id for code, row in regions.items()},
            **{code: row.id for code, row in hospitals.items()},
        }

    context = SecurityContext(
        user_id="local-synthetic-demo-owner",
        roles=frozenset({Role.ADMIN}),
        scope=DataScope.global_scope(),
    )
    service = MappingService(
        get_unit_of_work_factory(),
        get_authorization_service(),
        ClickHouseMappingRepository(get_client()),
    )
    version = ""
    for kind, space, source_key, target_code in specs:
        alias_id = service.register(
            context,
            kind=kind,
            source_system="ИС БГ",
            identity_space=space,
            source_key=source_key,
        )
        approve = service.approve if kind == "ORGANIZATION" else service.approve_region
        version = approve(
            context,
            alias_id,
            targets[target_code],
            "local-synthetic-demo-profile-v1",
            0,
        )
    snapshot = service.publish(context, version)
    print(f"Local synthetic demo exact mappings published: {len(specs)}")
    return snapshot.version


if __name__ == "__main__":
    publish()
