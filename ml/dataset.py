"""Deterministic daily aggregation and leakage-safe feature construction."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from statistics import fmean, pstdev

from ml.contracts import (
    FEATURE_SCHEMA_VERSION,
    DailyObservation,
    DatasetMetadata,
    FeatureRow,
    ForecastDataset,
)


def build_daily_dataset(
    rows: Iterable[tuple[date, int | float]],
    *,
    source_watermark: str,
    regions_included: tuple[str, ...] = (),
) -> ForecastDataset:
    """Build a dense calendar-day count series from already aggregated rows."""
    values: dict[date, float] = {}
    for observed_on, value in rows:
        if observed_on in values:
            raise ValueError(f"Duplicate daily aggregate for {observed_on.isoformat()}")
        if value < 0:
            raise ValueError("Referral count cannot be negative")
        values[observed_on] = float(value)
    if not values:
        raise ValueError("Referral history is empty")

    period_start = min(values)
    period_end = max(values)
    observations: list[DailyObservation] = []
    missing: list[date] = []
    current = period_start
    while current <= period_end:
        if current not in values:
            missing.append(current)
        observations.append(DailyObservation(current, values.get(current, 0.0)))
        current += timedelta(days=1)

    metadata = DatasetMetadata(
        period_start=period_start,
        period_end=period_end,
        row_count=len(observations),
        regions_included=regions_included,
        source_watermark=source_watermark,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        missing_dates=tuple(missing),
    )
    return ForecastDataset(tuple(observations), metadata)


def features_for_next(
    history: Sequence[tuple[date, float]], target_date: date
) -> tuple[float, ...]:
    """Features for one future day, calculated only from supplied history."""
    if len(history) < 7:
        raise ValueError("At least seven historical observations are required")
    values = [item[1] for item in history]
    window = values[-7:]
    return (
        values[-1],
        values[-2],
        values[-3],
        values[-7],
        fmean(window),
        pstdev(window),
        float(target_date.weekday()),
    )


def feature_rows(observations: Sequence[DailyObservation]) -> tuple[FeatureRow, ...]:
    """Build supervised rows; every feature precedes its target."""
    rows: list[FeatureRow] = []
    history: list[tuple[date, float]] = []
    for observation in observations:
        if len(history) >= 7:
            features = features_for_next(history, observation.observed_on)
            rows.append(
                FeatureRow(
                    target_date=observation.observed_on,
                    target=observation.value,
                    lag_1=features[0],
                    lag_2=features[1],
                    lag_3=features[2],
                    lag_7=features[3],
                    rolling_mean_7=features[4],
                    rolling_std_7=features[5],
                    day_of_week=int(features[6]),
                )
            )
        history.append((observation.observed_on, observation.value))
    return tuple(rows)
