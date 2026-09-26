"""Only invented records may populate the isolated acceptance project."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from data_pipeline.contracts import get_contract
from scripts.acceptance.synthetic_dataset import generate


def test_generates_four_contract_exact_synthetic_deliveries(tmp_path: Path) -> None:
    result = generate(tmp_path)
    assert result == {"REFERRALS": 30, "WAITING": 22, "REFUSALS": 24, "TREATED": 2}
    for dataset, count in result.items():
        contract = get_contract(dataset)
        source = tmp_path / contract.source_directory / "synthetic.csv"
        with source.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames == list(contract.column_names)
            assert len(list(reader)) == count
        manifest = json.loads((tmp_path / f"manifest-{dataset}.json").read_text())
        assert manifest["dataset_type"] == dataset
        assert manifest["expected_rows"] == count
        assert manifest["file_hashes"] == [
            hashlib.sha256(source.read_bytes()).hexdigest()
        ]
        assert manifest["mode"] == (
            "SNAPSHOT" if dataset in {"WAITING", "TREATED"} else "DELTA"
        )


def test_generation_does_not_overwrite_existing_source(tmp_path: Path) -> None:
    generate(tmp_path)
    with pytest.raises(FileExistsError):
        generate(tmp_path)
