from __future__ import annotations

from datetime import date, timedelta

from ml.forecasting.model import HistGradientBoostingForecaster


def test_hist_gradient_boosting_forecaster_is_deterministic() -> None:
    start = date(2025, 1, 1)
    history = [
        (start + timedelta(days=index), float(100 + index % 7)) for index in range(50)
    ]
    target = start + timedelta(days=50)

    first = HistGradientBoostingForecaster()
    second = HistGradientBoostingForecaster()
    first.fit(history)
    second.fit(history)

    assert first.predict_next(history, target) == second.predict_next(history, target)
