"""Local demo deliveries remain deterministic, synthetic, and contract-exact."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from data_pipeline.contracts import get_contract


EXPECTED_REGIONS = {
    "KZ-ASTANA",
    "KZ-ALMATY",
    "KZ-SHYMKENT",
    "KZ-ATYRAU",
    "KZ-AKTOBE",
    "KZ-KARAGANDA",
    "KZ-KOSTANAY",
    "KZ-KYZYLORDA",
    "KZ-PAVLODAR",
    "KZ-EAST",
    "KZ-WEST",
    "KZ-MANGYSTAU",
}


def _rows(root: Path, dataset: str) -> list[dict[str, str]]:
    source = root / get_contract(dataset).source_directory / "synthetic-local-demo.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_local_demo_deliveries_are_reproducible_and_auditable(tmp_path: Path) -> None:
    from scripts.local_demo.dataset import generate

    left, right = tmp_path / "left", tmp_path / "right"
    counts = generate(left)
    assert counts == generate(right)
    assert set(counts) == {"REFERRALS", "WAITING", "REFUSALS"}
    assert counts["WAITING"] == 60
    assert counts["REFUSALS"] == 156
    assert counts["REFERRALS"] > 1800
    for dataset, count in counts.items():
        left_manifest = json.loads(
            (left / f"manifest-{dataset}.json").read_text(encoding="utf-8")
        )
        right_manifest = json.loads(
            (right / f"manifest-{dataset}.json").read_text(encoding="utf-8")
        )
        source = left / get_contract(dataset).source_directory / "synthetic-local-demo.csv"
        assert left_manifest == right_manifest
        assert left_manifest["expected_rows"] == count == len(_rows(left, dataset))
        assert left_manifest["file_hashes"] == [
            hashlib.sha256(source.read_bytes()).hexdigest()
        ]


def test_every_source_identity_belongs_to_one_of_twelve_regions(tmp_path: Path) -> None:
    from scripts.local_demo.dataset import generate, load_profile

    assert {item["code"] for item in load_profile()} == EXPECTED_REGIONS
    generate(tmp_path)
    assert {
        row["hospital_mo"].removeprefix("SYN-ORG-")
        for row in _rows(tmp_path, "REFERRALS")
    } == EXPECTED_REGIONS
    assert {
        row["region_origin_code"].removeprefix("SYN-REG-")
        for row in _rows(tmp_path, "WAITING")
    } == EXPECTED_REGIONS
    assert {
        row["region_in"].removeprefix("SYN-REF-REG-")
        for row in _rows(tmp_path, "REFUSALS")
    } == EXPECTED_REGIONS


def test_local_demo_does_not_overwrite_an_existing_delivery(tmp_path: Path) -> None:
    from scripts.local_demo.dataset import generate

    generate(tmp_path)
    source = tmp_path / get_contract("REFERRALS").source_directory / "synthetic-local-demo.csv"
    before = source.read_bytes()
    with pytest.raises(FileExistsError):
        generate(tmp_path)
    assert source.read_bytes() == before
