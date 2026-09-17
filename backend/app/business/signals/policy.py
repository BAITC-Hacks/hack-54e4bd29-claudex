"""Versioned and validated Signal Engine analytical policy."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SignalPolicy:
    rule_version: str = "v1"
    freshness_max_age_hours: dict[str, int | None] = field(
        default_factory=lambda: {
            "REFERRALS": 72,
            "REFUSALS": 72,
            "WAITING": 168,
            "TREATED": None,
        }
    )
    spike_window_days: int = 7
    spike_reference_windows: int = 8
    warning_percent: float = 20.0
    high_percent: float = 35.0
    critical_percent: float = 50.0
    quality_warning_percent: float = 1.0
    quality_high_percent: float = 5.0
    quality_critical_percent: float = 10.0
    freshness_high_multiplier: float = 2.0
    freshness_critical_multiplier: float = 4.0

    def __post_init__(self) -> None:
        if self.spike_window_days < 1 or self.spike_reference_windows < 1:
            raise ValueError("Окна Signal Engine должны быть положительными")
        if not (0 < self.warning_percent < self.high_percent < self.critical_percent):
            raise ValueError("Пороги spike severity должны строго возрастать")
        if not (
            0
            < self.quality_warning_percent
            < self.quality_high_percent
            < self.quality_critical_percent
        ):
            raise ValueError("Пороги data-quality severity должны строго возрастать")
        if not (1 < self.freshness_high_multiplier < self.freshness_critical_multiplier):
            raise ValueError("Множители freshness severity должны строго возрастать")
