"""Operator CLI for exact identities, reviewed decisions and publication."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import cast
from uuid import UUID

from app.business.mapping.service import MappingService
from app.composition import get_unit_of_work_factory
from app.database.clickhouse import get_client
from app.repositories.clickhouse_mapping import (
    ClickHouseMappingRepository,
    ProjectionClient,
)
from app.security.authorization import get_authorization_service
from app.security.context import DataScope, Role, SecurityContext


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor", required=True, help="auditable operator subject")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register")
    register.add_argument("--kind", choices=["ORGANIZATION", "REGION"], required=True)
    register.add_argument("--source-system", required=True)
    register.add_argument("--identity-space", required=True)
    register.add_argument("--source-key", required=True)
    for action in ("approve", "revoke"):
        command = commands.add_parser(action)
        command.add_argument(
            "--kind", choices=["ORGANIZATION", "REGION"], default="ORGANIZATION"
        )
        command.add_argument("--alias-id", type=UUID, required=True)
        command.add_argument("--expected-version", type=int, required=True)
        command.add_argument("--evidence-ref", required=True)
        if action == "approve":
            command.add_argument("--target-id", type=UUID, required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    context = SecurityContext(
        user_id=args.actor, roles=frozenset({Role.ADMIN}), scope=DataScope.global_scope()
    )
    service = MappingService(
        get_unit_of_work_factory(),
        get_authorization_service(),
        ClickHouseMappingRepository(cast(ProjectionClient, get_client())),
    )
    if args.command == "register":
        print(
            service.register(
                context,
                kind=args.kind,
                source_system=args.source_system,
                identity_space=args.identity_space,
                source_key=args.source_key,
            )
        )
    elif args.command == "approve":
        approve = (
            service.approve if args.kind == "ORGANIZATION" else service.approve_region
        )
        print(
            approve(
                context,
                args.alias_id,
                args.target_id,
                args.evidence_ref,
                args.expected_version,
            )
        )
    elif args.command == "revoke":
        print(
            service.revoke(
                context,
                args.alias_id,
                args.evidence_ref,
                args.expected_version,
                kind=args.kind,
            )
        )
    else:
        snapshot = service.publish(context, args.version)
        print(f"{snapshot.version} {snapshot.digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
