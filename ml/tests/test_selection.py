from __future__ import annotations

from datetime import date

from ml.contracts import (
    CandidateEvaluation,
    FoldEvaluation,
    MetricSet,
    ValidationFold,
)
from ml.selection import select_candidate


def _candidate(
    name: str, mae: float, wape: float, rmse: float = 1.0
) -> CandidateEvaluation:
    return CandidateEvaluation(
        model_name=name,
        model_type="ML" if name == "hist_gradient_boosting" else "BASELINE",
        overall=MetricSet(mae=mae, wape=wape, rmse=rmse),
        folds=(),
    )


def _with_fold(
    candidate: CandidateEvaluation, *, mae: float, wape: float
) -> CandidateEvaluation:
    fold = ValidationFold(
        index=1,
        train_indices=tuple(range(42)),
        validation_indices=tuple(range(42, 49)),
        train_start=date(2025, 1, 1),
        train_end=date(2025, 2, 11),
        validation_start=date(2025, 2, 12),
        validation_end=date(2025, 2, 18),
    )
    return CandidateEvaluation(
        model_name=candidate.model_name,
        model_type=candidate.model_type,
        overall=candidate.overall,
        folds=(FoldEvaluation(fold, MetricSet(mae, wape, mae)),),
    )


def test_ml_wins_only_when_both_primary_metrics_improve_materially() -> None:
    result = select_candidate(
        baselines=(_candidate("naive_last", 10.0, 0.20),),
        ml=_candidate("hist_gradient_boosting", 9.0, 0.17),
        minimum_relative_improvement=0.02,
    )

    assert result.selected.model_name == "hist_gradient_boosting"


def test_strongest_baseline_wins_when_ml_improves_only_one_metric() -> None:
    result = select_candidate(
        baselines=(
            _candidate("naive_last", 10.0, 0.20),
            _candidate("weekly_naive", 11.0, 0.18),
        ),
        ml=_candidate("hist_gradient_boosting", 9.0, 0.20),
        minimum_relative_improvement=0.02,
    )

    assert result.selected.model_name == "naive_last"


def test_equal_or_near_equal_performance_keeps_baseline() -> None:
    result = select_candidate(
        baselines=(_candidate("moving_average_7", 10.0, 0.20),),
        ml=_candidate("hist_gradient_boosting", 9.9, 0.198),
        minimum_relative_improvement=0.02,
    )

    assert result.selected.model_name == "moving_average_7"


def test_overall_ml_win_is_rejected_when_one_fold_regresses() -> None:
    baseline = _with_fold(_candidate("weekly_naive", 10.0, 0.20), mae=8.0, wape=0.16)
    ml = _with_fold(
        _candidate("hist_gradient_boosting", 8.0, 0.15),
        mae=9.0,
        wape=0.18,
    )

    result = select_candidate(baselines=(baseline,), ml=ml)

    assert result.selected.model_name == "weekly_naive"
    assert result.ml_selected is False
    assert "stable fold-level performance" in result.rationale
