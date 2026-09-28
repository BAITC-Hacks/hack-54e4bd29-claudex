"""Shared walk-forward evaluation for baselines and the ML candidate."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from ml.baselines import BASELINES, Baseline
from ml.contracts import (
    CandidateEvaluation,
    FoldEvaluation,
    ForecastDataset,
    ForecastValue,
    TrainingResult,
    ValidationFold,
)
from ml.forecasting.model import HistGradientBoostingForecaster
from ml.metrics import calculate_metrics
from ml.selection import select_candidate
from ml.validation import rolling_origin_folds


class Forecaster(Protocol):
    def predict_next(
        self, history: Sequence[tuple[date, float]], target_date: date
    ) -> float: ...


ForecasterFactory = Callable[[], Forecaster]


def _fit(model: Forecaster, history: list[tuple[date, float]]) -> None:
    fit = getattr(model, "fit", None)
    if fit is not None:
        fit(history)


def _recursive_forecast(
    model: Forecaster,
    history: list[tuple[date, float]],
    target_dates: Sequence[date],
) -> list[float]:
    working = list(history)
    predictions: list[float] = []
    for target_date in target_dates:
        predicted = max(0.0, float(model.predict_next(working, target_date)))
        predictions.append(predicted)
        working.append((target_date, predicted))
    return predictions


def evaluate_candidate(
    dataset: ForecastDataset,
    folds: Sequence[ValidationFold],
    *,
    model_name: str,
    model_type: str,
    factory: ForecasterFactory,
) -> CandidateEvaluation:
    observations = dataset.observations
    fold_results: list[FoldEvaluation] = []
    all_actual: list[float] = []
    all_predicted: list[float] = []
    for fold in folds:
        history = [
            (observations[index].observed_on, observations[index].value)
            for index in fold.train_indices
        ]
        targets = [observations[index] for index in fold.validation_indices]
        model = factory()
        _fit(model, history)
        predicted = _recursive_forecast(
            model, history, [item.observed_on for item in targets]
        )
        actual = [item.value for item in targets]
        fold_results.append(
            FoldEvaluation(fold=fold, metrics=calculate_metrics(actual, predicted))
        )
        all_actual.extend(actual)
        all_predicted.extend(predicted)
    return CandidateEvaluation(
        model_name=model_name,
        model_type=model_type,
        overall=calculate_metrics(all_actual, all_predicted),
        folds=tuple(fold_results),
    )


def _baseline_factory(baseline: Baseline) -> ForecasterFactory:
    return lambda: baseline


def _baseline_by_name(name: str) -> Baseline:
    for baseline in BASELINES:
        if baseline.name == name:
            return baseline
    raise ValueError(f"Unknown baseline: {name}")


def run_training(
    dataset: ForecastDataset,
    *,
    horizon: int = 7,
    min_train_size: int = 42,
    minimum_relative_improvement: float = 0.02,
    ml_factory: ForecasterFactory | None = None,
    generated_at: datetime | None = None,
) -> TrainingResult:
    dates = tuple(item.observed_on for item in dataset.observations)
    folds = rolling_origin_folds(dates, horizon=horizon, min_train_size=min_train_size)
    baseline_evaluations = tuple(
        evaluate_candidate(
            dataset,
            folds,
            model_name=baseline.name,
            model_type="BASELINE",
            factory=_baseline_factory(baseline),
        )
        for baseline in BASELINES
    )
    actual_ml_factory = ml_factory or HistGradientBoostingForecaster
    ml_evaluation = evaluate_candidate(
        dataset,
        folds,
        model_name="hist_gradient_boosting",
        model_type="ML",
        factory=actual_ml_factory,
    )
    selection = select_candidate(
        baselines=baseline_evaluations,
        ml=ml_evaluation,
        minimum_relative_improvement=minimum_relative_improvement,
    )

    history = [(item.observed_on, item.value) for item in dataset.observations]
    selected_model: Forecaster
    if selection.ml_selected:
        selected_model = actual_ml_factory()
    else:
        selected_model = _baseline_by_name(selection.selected.model_name)
    _fit(selected_model, history)
    baseline_model = _baseline_by_name(selection.strongest_baseline.model_name)
    future_dates = [
        dataset.metadata.period_end + timedelta(days=offset)
        for offset in range(1, horizon + 1)
    ]
    predictions = _recursive_forecast(selected_model, history, future_dates)
    baseline_predictions = _recursive_forecast(baseline_model, history, future_dates)
    forecast = tuple(
        ForecastValue(target_date, predicted, baseline)
        for target_date, predicted, baseline in zip(
            future_dates, predictions, baseline_predictions, strict=True
        )
    )
    return TrainingResult(
        generated_at=generated_at or datetime.now(UTC),
        dataset=dataset,
        evaluations=(*baseline_evaluations, ml_evaluation),
        selection=selection,
        forecast=forecast,
    )


__all__ = ["evaluate_candidate", "run_training"]
