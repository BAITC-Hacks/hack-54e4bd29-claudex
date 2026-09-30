"""A reused local demo delivery must fail before any seed or import."""

from __future__ import annotations

import pytest


def test_preflight_rejects_existing_delivery_id() -> None:
    from seeds.local_demo_preflight import assert_unused_delivery_ids

    requested = (
        "phase8-synthetic-local-demo-referrals-v1",
        "phase8-synthetic-local-demo-waiting-v1",
        "phase8-synthetic-local-demo-refusals-v1",
    )
    assert_unused_delivery_ids(requested, ())
    with pytest.raises(RuntimeError, match="already exists"):
        assert_unused_delivery_ids(requested, (requested[1],))
    with pytest.raises(ValueError, match="delivery IDs"):
        assert_unused_delivery_ids(requested[:2], ())
