"""Conservative candidate selection: a strong baseline is a valid winner."""

from __future__ import annotations

from collections.abc import Sequence
from math import inf

from ml.contracts import CandidateEvaluation, SelectionResult


def _sort_key(candidate: CandidateEvaluation) -> tuple[float, float, float, str]:
    return (
        candidate.overall.mae,
        candidate.overall.wape if candidate.overall.wape is not None else inf,
        candidate.overall.rmse,
        candidate.model_name,
    )


def _stable_across_folds(ml: CandidateEvaluation, baseline: CandidateEvaluation) -> bool:
    """Require ML to avoid regressions on every comparable validation fold."""
    if not ml.folds and not baseline.folds:
        return True
    if len(ml.folds) != len(baseline.folds):
        return False
    for ml_fold, baseline_fold in zip(ml.folds, baseline.folds, strict=True):
        if ml_fold.fold.index != baseline_fold.fold.index:
            return False
        ml_wape = ml_fold.metrics.wape
        baseline_wape = baseline_fold.metrics.wape
        if ml_wape is None or baseline_wape is None:
            return False
        if ml_fold.metrics.mae > baseline_fold.metrics.mae or ml_wape > baseline_wape:
            return False
    return True


def select_candidate(
    *,
    baselines: Sequence[CandidateEvaluation],
    ml: CandidateEvaluation,
    minimum_relative_improvement: float = 0.02,
) -> SelectionResult:
    if not baselines:
        raise ValueError("At least one baseline is required")
    baseline = min(baselines, key=_sort_key)
    threshold = 1.0 - minimum_relative_improvement
    baseline_wape = baseline.overall.wape
    ml_wape = ml.overall.wape
    ml_wins = False
    stable = _stable_across_folds(ml, baseline)
    if baseline_wape is not None and ml_wape is not None:
        ml_wins = (
            ml.overall.mae <= baseline.overall.mae * threshold
            and ml_wape <= baseline_wape * threshold
            and stable
        )
    if ml_wins:
        return SelectionResult(
            selected=ml,
            strongest_baseline=baseline,
            ml_selected=True,
            rationale=(
                "ML improved both MAE and WAPE by at least "
                f"{minimum_relative_improvement:.0%} and did not regress on any fold."
            ),
        )
    return SelectionResult(
        selected=baseline,
        strongest_baseline=baseline,
        ml_selected=False,
        rationale=(
            "The ML candidate did not improve both MAE and WAPE by the "
            f"required {minimum_relative_improvement:.0%} with stable fold-level "
            "performance; the strongest baseline remains selected."
        ),
    )
