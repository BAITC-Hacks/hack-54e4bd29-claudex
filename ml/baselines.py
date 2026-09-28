"""First-class short-horizon baseline forecasters."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from statistics import fmean
from typing import Protocol


class Baseline(Protocol):
    name: str

    def predict_next(
        self, history: Sequence[tuple[date, float]], target_date: date
    ) -> float: ...


class NaiveLastValue:
    name = "naive_last"

    def predict_next(
        self, history: Sequence[tuple[date, float]], target_date: date
    ) -> float:
        del target_date
        if not history:
            raise ValueError("History is empty")
        return history[-1][1]


class WeeklyNaive:
    name = "weekly_naive"

    def predict_next(
        self, history: Sequence[tuple[date, float]], target_date: date
    ) -> float:
        del target_date
        if len(history) < 7:
            raise ValueError("Weekly naive requires seven observations")
        return history[-7][1]


class MovingAverage7:
    name = "moving_average_7"

    def predict_next(
        self, history: Sequence[tuple[date, float]], target_date: date
    ) -> float:
        del target_date
        if len(history) < 7:
            raise ValueError("Moving average requires seven observations")
        return fmean(item[1] for item in history[-7:])


BASELINES: tuple[Baseline, ...] = (
    NaiveLastValue(),
    WeeklyNaive(),
    MovingAverage7(),
)
