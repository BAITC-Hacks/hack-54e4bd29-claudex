"""Pure deterministic calculations for Phase 7 scenarios."""

from decimal import ROUND_HALF_UP, Decimal

from app.business.simulation.contracts import ScenarioCalculation
from app.core.exceptions import ValidationError

PRECISION = Decimal("0.0001")
SUPPORTED_ASSUMPTIONS = frozenset(
    {Decimal("-0.20"), Decimal("-0.10"), Decimal("0.10"), Decimal("0.20")}
)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(PRECISION, rounding=ROUND_HALF_UP)


def calculate_referral_inflow_change(
    baseline_value: Decimal, assumption_value: Decimal
) -> ScenarioCalculation:
    """Apply a fixed inflow assumption to a positive authoritative baseline."""
    if assumption_value not in SUPPORTED_ASSUMPTIONS:
        raise ValidationError("Неподдерживаемое допущение сценария")
    if baseline_value <= 0:
        raise ValidationError("Baseline должен быть положительным")

    baseline = _quantize(baseline_value)
    calculated = _quantize(baseline * (Decimal("1") + assumption_value))
    return ScenarioCalculation(
        baseline_value=baseline,
        assumption_value=assumption_value,
        calculated_value=calculated,
        delta_absolute=_quantize(calculated - baseline),
        delta_percent=assumption_value,
    )


__all__ = ["SUPPORTED_ASSUMPTIONS", "calculate_referral_inflow_change"]
