from __future__ import annotations

from math import sqrt

import pytest

from ml.metrics import calculate_metrics


def test_metrics_are_calculated_from_the_same_actual_prediction_pairs() -> None:
    result = calculate_metrics([10.0, 20.0], [8.0, 24.0])

    assert result.mae == pytest.approx(3.0)
    assert result.wape == pytest.approx(0.2)
    assert result.rmse == pytest.approx(sqrt(10.0))


def test_wape_is_undefined_when_actual_denominator_is_zero() -> None:
    result = calculate_metrics([0.0, 0.0], [1.0, 2.0])

    assert result.wape is None
    assert result.mae == pytest.approx(1.5)
