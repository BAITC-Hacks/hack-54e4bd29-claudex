"""The forecast demo extension must stay deterministic and synthetic."""

import csv
import hashlib
import json

import pytest

from scripts.acceptance.forecast_demo_fixture import generate


def test_forecast_fixture_is_reproducible_and_non_destructive(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    source_a, manifest_a = generate(first)
    source_b, manifest_b = generate(second)
    assert source_a.read_bytes() == source_b.read_bytes()
    assert json.loads(manifest_a.read_text()) == json.loads(manifest_b.read_text())
    with source_a.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) > 42 + 7
    assert {row["registration_dt"][:10] for row in rows} == {
        f"2025-01-{day:02d}" for day in range(3, 32)
    } | {f"2025-02-{day:02d}" for day in range(1, 29)} | {
        f"2025-03-{day:02d}" for day in range(1, 32)
    }
    assert all(
        row["hospitalization_code"].startswith("SYNTHETIC-FORECAST-") for row in rows
    )
    manifest = json.loads(manifest_a.read_text())
    assert manifest["file_hashes"] == [hashlib.sha256(source_a.read_bytes()).hexdigest()]
    with pytest.raises(FileExistsError):
        generate(first)
