"""Local synthetic evidence must reconcile to source, scope, and forecast."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.local_demo.dataset import generate, load_profile


def test_expected_counts_rejects_tampered_source_hash(tmp_path: Path) -> None:
    from scripts.local_demo.verify import expected_counts

    generate(tmp_path)
    manifest = tmp_path / "manifest-REFERRALS.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["file_hashes"] = ["0" * 64]
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        expected_counts(tmp_path)


def test_expected_counts_rejects_wrong_row_count(tmp_path: Path) -> None:
    from scripts.local_demo.verify import expected_counts

    generate(tmp_path)
    manifest = tmp_path / "manifest-WAITING.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["expected_rows"] += 1
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="count"):
        expected_counts(tmp_path)


def test_expected_counts_match_generated_manifests(tmp_path: Path) -> None:
    from scripts.local_demo.verify import expected_counts, expected_region_counts

    generated = generate(tmp_path)
    assert expected_counts(tmp_path) == generated
    by_region = expected_region_counts(tmp_path)
    assert set(by_region) == {item["code"] for item in load_profile()}
    assert tuple(sum(row[index] for row in by_region.values()) for index in range(3)) == (
        generated["REFERRALS"],
        generated["WAITING"],
        generated["REFUSALS"],
    )


def test_region_coverage_requires_exact_canonical_targets() -> None:
    from scripts.local_demo.verify import assert_region_coverage

    expected = {item["code"] for item in load_profile()}
    with pytest.raises(AssertionError, match="region coverage"):
        assert_region_coverage(expected, expected - {"KZ-ASTANA"})
    with pytest.raises(AssertionError, match="region coverage"):
        assert_region_coverage(expected, expected | {"KZ-EXTRA"})


def test_published_mapping_snapshot_requires_exact_aliases_and_targets() -> None:
    from scripts.local_demo.verify_mappings_db import assert_exact_mappings

    targets = {"H-KZ-ASTANA": "hospital-1", "KZ-ASTANA": "region-1"}
    specs = (
        ("ORGANIZATION", "IS_BG:REFERRALS:RECEIVING", "syn-org-kz-astana", "H-KZ-ASTANA"),
        ("REGION", "IS_BG:WAITING:REGION", "SYN-REG-KZ-ASTANA", "KZ-ASTANA"),
    )
    actual = (
        ("ORGANIZATION", "IS_BG:REFERRALS:RECEIVING", "syn-org-kz-astana", "hospital-1"),
        ("REGION", "IS_BG:WAITING:REGION", "SYN-REG-KZ-ASTANA", "region-1"),
    )
    assert_exact_mappings(specs, targets, actual)
    with pytest.raises(AssertionError, match="snapshot"):
        assert_exact_mappings(specs, targets, actual[:-1])
    with pytest.raises(AssertionError, match="snapshot"):
        assert_exact_mappings(specs, targets, (actual[0], actual[0]))
    with pytest.raises(AssertionError, match="snapshot"):
        assert_exact_mappings(
            specs, targets, (actual[0], (*actual[1][:3], "wrong-region"))
        )


def test_forecast_contract_rejects_wrong_horizon_or_cutoff() -> None:
    from scripts.local_demo.verify import assert_forecast_contract

    forecast = {
        "target": "DAILY_REFERRAL_COUNT",
        "scope_type": "GLOBAL",
        "horizon_days": 7,
        "input_period_end": "2025-03-31T23:59:59Z",
        "forecast_start": "2025-04-01",
        "forecast_end": "2025-04-07",
        "validation_period_start": "2025-02-01",
        "validation_period_end": "2025-03-30",
        "model_version": "synthetic-test",
        "metrics": {"mae": 1.5},
        "baseline_metrics": {"mae": 2.0},
        "forecast": [{"date": f"2025-04-{day:02d}"} for day in range(1, 8)],
    }
    assert_forecast_contract(forecast)
    with pytest.raises(AssertionError, match="horizon"):
        assert_forecast_contract({**forecast, "horizon_days": 6})
    with pytest.raises(AssertionError, match="cutoff"):
        assert_forecast_contract({**forecast, "input_period_end": "2025-03-30T00:00:00Z"})


def test_persisted_forecast_requires_seven_ordered_points() -> None:
    from scripts.local_demo.verify_forecast_db import assert_persisted_contract

    record = {
        "target": "DAILY_REFERRAL_COUNT",
        "scope_type": "GLOBAL",
        "horizon_days": 7,
        "input_period_end": "2025-03-31",
        "forecast_start": "2025-04-01",
        "forecast_end": "2025-04-07",
        "model_version": "synthetic-test",
        "validation_mae": 1.5,
        "baseline_mae": 2.0,
        "point_dates": [f"2025-04-{day:02d}" for day in range(1, 8)],
    }
    assert_persisted_contract(record)
    with pytest.raises(AssertionError, match="point"):
        assert_persisted_contract({**record, "point_dates": record["point_dates"][:-1]})


def test_persisted_summary_mae_allows_only_storage_rounding() -> None:
    from scripts.local_demo.verify_forecast_db import assert_summary_mae

    assert_summary_mae(1.595238, 1.5952380952380953)
    with pytest.raises(AssertionError, match="MAE"):
        assert_summary_mae(1.5953, 1.5952380952380953)
