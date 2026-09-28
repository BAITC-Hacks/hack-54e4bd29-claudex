from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.adapters.forecasting import ReferralForecastEngine
from app.business.forecasting.contracts import (
    DailyReferralCount,
    ReferralDatasetWatermark,
)


class Tracked:
    run_id = "run-1"
    model_version = "referrals-global-20250311-run1"


class Tracker:
    def __init__(self) -> None:
        self.result = None

    def track(self, result):
        self.result = result
        return Tracked()


def test_adapter_maps_framework_independent_training_result() -> None:
    start = date(2025, 1, 1)
    history = tuple(
        DailyReferralCount(start + timedelta(days=index), 100 + index % 7)
        for index in range(70)
    )
    tracker = Tracker()
    engine = ReferralForecastEngine(tracker=tracker)

    result = engine.train(
        history,
        ReferralDatasetWatermark(
            completed_at=datetime(2025, 4, 1, tzinfo=UTC),
            import_ids=(uuid.uuid4(),),
            file_hashes=("a" * 64,),
        ),
        generated_at=datetime(2025, 4, 2, tzinfo=UTC),
    )

    assert tracker.result is not None
    assert result.training_rows == 70
    assert result.mlflow_run_id == "run-1"
    assert len(result.points) == 7
    assert len(result.validation_folds) == 4
