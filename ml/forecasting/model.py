"""The single Phase 5A tabular ML candidate."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sklearn.ensemble import HistGradientBoostingRegressor

from ml.contracts import DailyObservation
from ml.dataset import feature_rows, features_for_next


class HistGradientBoostingForecaster:
    """Small deterministic regressor for recursive seven-day inference."""

    name = "hist_gradient_boosting"

    def __init__(self) -> None:
        self._model = HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_iter=150,
            max_leaf_nodes=15,
            min_samples_leaf=5,
            l2_regularization=0.1,
            random_state=42,
        )
        self._fitted = False

    def fit(self, history: Sequence[tuple[date, float]]) -> None:
        rows = feature_rows(
            tuple(DailyObservation(observed_on, value) for observed_on, value in history)
        )
        if len(rows) < 14:
            raise ValueError("ML training requires at least 21 daily observations")
        self._model.fit(
            [list(row.features) for row in rows],
            [row.target for row in rows],
        )
        self._fitted = True

    def predict_next(
        self, history: Sequence[tuple[date, float]], target_date: date
    ) -> float:
        if not self._fitted:
            raise RuntimeError("Model is not fitted")
        features = features_for_next(history, target_date)
        prediction = float(self._model.predict([list(features)])[0])
        return max(0.0, prediction)

    @property
    def estimator(self) -> HistGradientBoostingRegressor:
        if not self._fitted:
            raise RuntimeError("Model is not fitted")
        return self._model
