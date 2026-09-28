from __future__ import annotations

from datetime import date, timedelta

from ml.dataset import build_daily_dataset, feature_rows


def test_daily_dataset_fills_missing_calendar_dates_and_records_them() -> None:
    rows = [(date(2025, 1, 1), 10), (date(2025, 1, 3), 30)]

    dataset = build_daily_dataset(rows, source_watermark="imports:1")

    assert [item.value for item in dataset.observations] == [10.0, 0.0, 30.0]
    assert dataset.metadata.missing_dates == (date(2025, 1, 2),)
    assert dataset.metadata.row_count == 3
    assert dataset.metadata.feature_schema_version == "referrals_daily_v1"


def test_feature_rows_use_only_values_before_the_target_date() -> None:
    start = date(2025, 1, 1)
    observations = [(start + timedelta(days=i), i + 1) for i in range(10)]
    dataset = build_daily_dataset(observations, source_watermark="imports:1")

    rows = feature_rows(dataset.observations)

    first = rows[0]
    assert first.target_date == date(2025, 1, 8)
    assert first.target == 8.0
    assert first.lag_1 == 7.0
    assert first.lag_2 == 6.0
    assert first.lag_3 == 5.0
    assert first.lag_7 == 1.0
    assert first.rolling_mean_7 == 4.0


def test_future_target_changes_do_not_change_earlier_features() -> None:
    start = date(2025, 1, 1)
    base = [(start + timedelta(days=i), i + 1) for i in range(12)]
    changed = list(base)
    changed[-1] = (changed[-1][0], 999_999)

    before = feature_rows(build_daily_dataset(base, source_watermark="x").observations)
    after = feature_rows(build_daily_dataset(changed, source_watermark="x").observations)

    assert before[-2].features == after[-2].features
