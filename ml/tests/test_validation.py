from __future__ import annotations

from datetime import date, timedelta

from ml.validation import rolling_origin_folds


def test_rolling_origin_folds_are_chronological_deterministic_and_non_overlapping() -> (
    None
):
    dates = tuple(date(2025, 1, 1) + timedelta(days=i) for i in range(70))

    first = rolling_origin_folds(dates, horizon=7, min_train_size=42)
    second = rolling_origin_folds(dates, horizon=7, min_train_size=42)

    assert first == second
    assert len(first) == 4
    for fold in first:
        assert fold.train_indices[-1] < fold.validation_indices[0]
        assert set(fold.train_indices).isdisjoint(fold.validation_indices)
        assert len(fold.validation_indices) == 7
        assert fold.train_end < fold.validation_start
