"""Read-only guard against replaying a local synthetic delivery ID."""

from __future__ import annotations

import argparse
import os

from sqlalchemy import select

from app.core.config import get_settings
from app.database.postgres import session_scope
from app.models.delivery import Delivery
from seeds.local_demo_seed import require_local_demo

EXPECTED_IDS = (
    "phase8-synthetic-local-demo-referrals-v1",
    "phase8-synthetic-local-demo-waiting-v1",
    "phase8-synthetic-local-demo-refusals-v1",
)


def assert_unused_delivery_ids(
    requested: tuple[str, ...], existing: tuple[str, ...]
) -> None:
    if requested != EXPECTED_IDS:
        raise ValueError("Unexpected local synthetic delivery IDs")
    if existing:
        raise RuntimeError("Local synthetic delivery ID already exists")


def preflight(requested: tuple[str, ...]) -> None:
    """Fail before generation, canonical seed, approval, or import writes."""
    require_local_demo(get_settings().app_env, os.getenv("LOCAL_SYNTHETIC_DEMO"))
    assert_unused_delivery_ids(requested, ())
    with session_scope() as session:
        existing = tuple(
            session.scalars(
                select(Delivery.delivery_id).where(Delivery.delivery_id.in_(requested))
            ).all()
        )
    assert_unused_delivery_ids(requested, existing)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery_ids", nargs="+")
    args = parser.parse_args()
    preflight(tuple(args.delivery_ids))
    print("Local synthetic delivery IDs are unused")


if __name__ == "__main__":
    main()
