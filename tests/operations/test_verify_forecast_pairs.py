"""MAE evidence is computed from chronological observation/prediction pairs."""

import json
from datetime import date, timedelta

from ml.validation import rolling_origin_folds
from scripts.acceptance.forecast_demo_fixture import generate as generate_forecast
from scripts.acceptance.synthetic_dataset import generate as generate_bootstrap
from scripts.acceptance.verify_forecast_pairs import (
    verify_source_fixture,
    weekly_naive_errors,
)


def test_weekly_naive_errors_use_prior_week_and_separate_validation():
    start = date(2025, 1, 1)
    observations = tuple((start + timedelta(days=i), float(i + 1)) for i in range(14))
    folds = rolling_origin_folds(
        tuple(day for day, _ in observations), horizon=7, min_train_size=7
    )
    pairs = weekly_naive_errors(observations, folds)
    assert len(pairs) == 7
    assert [actual - predicted for _, actual, predicted in pairs] == [7.0] * 7
    assert all(day > folds[0].train_end for day, _, _ in pairs)


def test_hashed_synthetic_sources_reproduce_api_mae(tmp_path):
    project = tmp_path / "phase8-forecast-test"
    project.mkdir()
    (project / "manifest.json").write_text(
        json.dumps({"project": project.name, "dataset": "synthetic-only"})
    )
    generate_bootstrap(project / "source-empty")
    generate_forecast(project / "source-forecast")
    result = verify_source_fixture(project, 1.5714285714285714)
    assert result["rows"] == 2019
    assert result["validation_pairs"] == 42
    assert result["matches_api_mae"] is True
