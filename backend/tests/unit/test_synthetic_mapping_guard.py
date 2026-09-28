"""Exact synthetic acceptance mappings must not run on an ordinary stack."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from scripts.acceptance import publish_synthetic_mappings

from app.core.config import AppEnv


def test_mapping_fixture_requires_explicit_local_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        publish_synthetic_mappings,
        "get_settings",
        lambda: SimpleNamespace(app_env=AppEnv.LOCAL),
    )
    monkeypatch.delenv("PHASE8_SYNTHETIC_ACCEPTANCE", raising=False)
    with pytest.raises(RuntimeError, match="explicit local opt-in"):
        publish_synthetic_mappings._guard()
    monkeypatch.setenv("PHASE8_SYNTHETIC_ACCEPTANCE", "1")
    publish_synthetic_mappings._guard()
    monkeypatch.setattr(
        publish_synthetic_mappings,
        "get_settings",
        lambda: SimpleNamespace(app_env=AppEnv.PRODUCTION),
    )
    with pytest.raises(RuntimeError, match="explicit local opt-in"):
        publish_synthetic_mappings._guard()


def test_synthetic_mapping_specs_do_not_overlap_identity_spaces() -> None:
    specs = publish_synthetic_mappings.SPECS
    assert len(specs) == 10
    assert len({(kind, space, source) for kind, space, source, _ in specs}) == len(specs)
