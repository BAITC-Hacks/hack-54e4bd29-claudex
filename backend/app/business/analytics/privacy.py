"""Small-cell suppression for sensitive analytics values."""

from __future__ import annotations

from typing import TypeVar

from app.business.analytics.contracts import AnalyticsCell

DEFAULT_SUPPRESSION_THRESHOLD = 10

ValueT = TypeVar("ValueT", int, float)


def suppress_small_cell(
    value: ValueT,
    cell_size: int,
    threshold: int = DEFAULT_SUPPRESSION_THRESHOLD,
) -> AnalyticsCell[ValueT]:
    """Hide an exact value when its contributing cell is below the threshold."""
    if cell_size < threshold:
        return AnalyticsCell(value=None, suppressed=True)
    return AnalyticsCell(value=value, suppressed=False)
