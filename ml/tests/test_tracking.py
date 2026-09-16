from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import mlflow

from ml.contracts import DailyObservation, DatasetMetadata, ForecastDataset
from ml.evaluation import run_training
from ml.tracking import MlflowExperimentTracker


class ConstantForecaster:
    def fit(self, history: Sequence[tuple[date, float]]) -> None:
        del history

    def predict_next(
        self, history: Sequence[tuple[date, float]], target_date: date
    ) -> float:
        del history, target_date
        return 10.0


def test_mlflow_records_selection_metrics_and_registered_artifact(
    tmp_path: Path,
) -> None:
    tracking_uri = (tmp_path / "mlruns").as_uri()
    mlflow.set_tracking_uri(tracking_uri)
    start = date(2025, 1, 1)
    observations = tuple(
        DailyObservation(start + timedelta(days=index), float(10 + index % 7))
        for index in range(56)
    )
    dataset = ForecastDataset(
        observations,
        DatasetMetadata(
            period_start=start,
            period_end=observations[-1].observed_on,
            row_count=56,
            regions_included=(),
            source_watermark="wm-1",
            feature_schema_version="referrals_daily_v1",
            missing_dates=(),
        ),
    )
    result = run_training(
        dataset,
        min_train_size=42,
        ml_factory=ConstantForecaster,
    )
    tracker = MlflowExperimentTracker(
        tracking_uri=tracking_uri,
        experiment_name="test-referrals",
        registered_model_name="test-referral-model",
    )

    tracked = tracker.track(result)

    run = mlflow.get_run(tracked.run_id)
    assert run.data.params["forecast_horizon"] == "7"
    assert run.data.params["feature_schema_version"] == "referrals_daily_v1"
    assert "selected_mae" in run.data.metrics
    assert tracked.model_version.startswith("referrals-global-")
    versions = mlflow.search_model_versions(filter_string="name='test-referral-model'")
    assert len(versions) == 1
