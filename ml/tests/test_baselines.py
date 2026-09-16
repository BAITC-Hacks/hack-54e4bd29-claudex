from __future__ import annotations

from datetime import date, timedelta

import pytest

from ml.baselines import Baseline, MovingAverage7, NaiveLastValue, WeeklyNaive


def _history() -> list[tuple[date, float]]:
    start = date(2025, 1, 1)
    return [(start + timedelta(days=i), float(i + 1)) for i in range(7)]


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (NaiveLastValue(), 7.0),
        (WeeklyNaive(), 1.0),
        (MovingAverage7(), 4.0),
    ],
)
def test_baseline_uses_only_the_supplied_history(
    model: Baseline, expected: float
) -> None:
    assert model.predict_next(_history(), date(2025, 1, 8)) == expected
