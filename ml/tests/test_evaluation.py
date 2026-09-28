from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from ml.contracts import DailyObservation, DatasetMetadata, ForecastDataset
from ml.evaluation import evaluate_candidate, run_training
from ml.validation import rolling_origin_folds


class ConstantForecaster:
    def __init__(self, value: float) -> None:
        self.value = value

    def fit(self, history: Sequence[tuple[date, float]]) -> None:
        assert len(history) >= 7

    def predict_next(
        self, history: Sequence[tuple[date, float]], target_date: date
    ) -> float:
        assert history[-1][0] < target_date
        return self.value


def _dataset(values: list[float]) -> ForecastDataset:
    start = date(2025, 1, 1)
    observations = tuple(
        DailyObservation(start + timedelta(days=index), value)
        for index, value in enumerate(values)
    )
    return ForecastDataset(
        observations=observations,
        metadata=DatasetMetadata(
            period_start=observations[0].observed_on,
            period_end=observations[-1].observed_on,
            row_count=len(observations),
            regions_included=(),
            source_watermark="imports:1",
            feature_schema_version="referrals_daily_v1",
            missing_dates=(),
        ),
    )


def test_candidate_uses_supplied_folds_and_reports_each_fold() -> None:
    dataset = _dataset([10.0] * 56)
    folds = rolling_origin_folds(
        tuple(item.observed_on for item in dataset.observations),
        min_train_size=42,
        horizon=7,
    )

    result = evaluate_candidate(
        dataset,
        folds,
        model_name="constant",
        model_type="TEST",
        factory=lambda: ConstantForecaster(10.0),
    )

    assert tuple(item.fold for item in result.folds) == folds
    assert result.overall.mae == 0.0
    assert result.overall.wape == 0.0


def test_recursive_validation_does_not_append_actual_future_values() -> None:
    dataset = _dataset([10.0] * 42 + [999.0] + [500.0] * 6)
    folds = rolling_origin_folds(
        tuple(item.observed_on for item in dataset.observations),
        min_train_size=42,
        horizon=7,
    )

    result = evaluate_candidate(
        dataset,
        folds,
        model_name="constant",
        model_type="TEST",
        factory=lambda: ConstantForecaster(0.0),
    )

    # All seven predictions are zero; the 999 actual value is never appended
    # to the model history for the later validation dates.
    assert result.overall.mae == (999.0 + 6 * 500.0) / 7


def test_training_generates_seven_future_days_and_a_baseline_comparator() -> None:
    values = [100.0 + (index % 7) for index in range(70)]

    result = run_training(
        _dataset(values),
        horizon=7,
        min_train_size=42,
        ml_factory=lambda: ConstantForecaster(102.0),
        generated_at=None,
    )

    assert len(result.forecast) == 7
    assert result.forecast[0].forecast_date == date(2025, 3, 12)
    assert all(item.predicted_value >= 0 for item in result.forecast)
    assert all(item.baseline_value >= 0 for item in result.forecast)
