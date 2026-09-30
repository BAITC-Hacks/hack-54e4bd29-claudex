"""Every invented source identifier has one exact canonical target."""

from __future__ import annotations

import pytest


def test_local_mapping_covers_five_identity_spaces_per_region() -> None:
    from seeds.local_demo_mappings import mapping_specs
    from seeds.local_demo_seed import load_profile

    specs = mapping_specs(load_profile())
    assert len(specs) == 60
    assert len({(kind, space, key) for kind, space, key, _ in specs}) == 60
    assert {
        target for _, _, _, target in specs if target.startswith("KZ-")
    } == {item["code"] for item in load_profile()}
    assert (
        "ORGANIZATION",
        "IS_BG:REFERRALS:RECEIVING",
        "SYN-ORG-KZ-ASTANA",
        "H-KZ-ASTANA",
    ) in specs
    assert (
        "REGION",
        "IS_BG:REFUSALS:REGION",
        "SYN-REF-REG-KZ-MANGYSTAU",
        "KZ-MANGYSTAU",
    ) in specs


def test_local_mapping_rejects_missing_or_foreign_targets() -> None:
    from seeds.local_demo_mappings import validate_directory
    from seeds.local_demo_seed import load_profile

    profile = load_profile()
    region_codes = {item["code"] for item in profile}
    hospital_codes = {f"H-{item['code']}" for item in profile}
    validate_directory(profile, region_codes, hospital_codes)
    with pytest.raises(RuntimeError, match="canonical directory"):
        validate_directory(profile, region_codes - {"KZ-ASTANA"}, hospital_codes)
    with pytest.raises(RuntimeError, match="canonical directory"):
        validate_directory(profile, region_codes | {"R-A"}, hospital_codes)
    with pytest.raises(RuntimeError, match="canonical directory"):
        validate_directory(profile, region_codes, hospital_codes - {"H-KZ-ASTANA"})
