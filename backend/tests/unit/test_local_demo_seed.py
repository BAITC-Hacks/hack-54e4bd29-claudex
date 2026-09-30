"""The local profile must not seed another environment or invent evidence."""

from __future__ import annotations

import pytest

from app.core.config import AppEnv


@pytest.mark.parametrize(
    ("environment", "opt_in"),
    [
        (AppEnv.PRODUCTION, "1"),
        (AppEnv.DEV, "1"),
        (AppEnv.LOCAL, None),
        (AppEnv.LOCAL, "0"),
    ],
)
def test_local_seed_rejects_unsafe_environment(
    environment: AppEnv, opt_in: str | None
) -> None:
    from seeds.local_demo_seed import require_local_demo

    with pytest.raises(RuntimeError, match="explicit local opt-in"):
        require_local_demo(environment, opt_in)


def test_local_seed_uses_reviewed_canonical_directory() -> None:
    from seeds.local_demo_seed import load_profile

    profile = load_profile()
    assert len(profile) == 12
    assert profile[0] == {"code": "KZ-ASTANA", "name": "Астана"}
    assert profile[-1] == {"code": "KZ-MANGYSTAU", "name": "Мангистауская область"}
    assert len({item["code"] for item in profile}) == 12


def test_local_signal_evidence_states_only_the_historical_cutoff() -> None:
    from seeds.local_demo_seed import signal_evidence

    evidence = signal_evidence()
    assert evidence == {
        "synthetic": True,
        "confirmed_complete_through": "2025-03-31",
    }
    assert "forecast_id" not in evidence
