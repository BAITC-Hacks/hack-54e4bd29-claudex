"""Chronological rolling-origin validation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from itertools import pairwise

from ml.contracts import ValidationFold


def rolling_origin_folds(
    dates: Sequence[date],
    *,
    horizon: int = 7,
    min_train_size: int = 42,
    step: int | None = None,
) -> tuple[ValidationFold, ...]:
    if horizon < 1 or min_train_size < 7:
        raise ValueError("Invalid validation window")
    if any(left >= right for left, right in pairwise(dates)):
        raise ValueError("Dates must be strictly increasing")
    stride = step or horizon
    folds: list[ValidationFold] = []
    origin = min_train_size
    while origin + horizon <= len(dates):
        validation = tuple(range(origin, origin + horizon))
        train = tuple(range(origin))
        folds.append(
            ValidationFold(
                index=len(folds) + 1,
                train_indices=train,
                validation_indices=validation,
                train_start=dates[0],
                train_end=dates[origin - 1],
                validation_start=dates[origin],
                validation_end=dates[origin + horizon - 1],
            )
        )
        origin += stride
    if not folds:
        raise ValueError("History is too short for one validation fold")
    return tuple(folds)
