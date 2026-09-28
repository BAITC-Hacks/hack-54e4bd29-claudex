"""Forecast metrics with explicit undefined-value behavior."""

from __future__ import annotations

from collections.abc import Sequence
from math import sqrt
from statistics import fmean

from ml.contracts import MetricSet


def calculate_metrics(actual: Sequence[float], predicted: Sequence[float]) -> MetricSet:
    if not actual or len(actual) != len(predicted):
        raise ValueError("Actual and predicted values must have equal non-zero length")
    absolute_errors = [abs(a - p) for a, p in zip(actual, predicted, strict=True)]
    squared_errors = [(a - p) ** 2 for a, p in zip(actual, predicted, strict=True)]
    denominator = sum(abs(item) for item in actual)
    return MetricSet(
        mae=fmean(absolute_errors),
        wape=sum(absolute_errors) / denominator if denominator else None,
        rmse=sqrt(fmean(squared_errors)),
    )
