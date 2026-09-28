from decimal import Decimal

import pytest

from app.business.simulation.calculation import calculate_referral_inflow_change
from app.core.exceptions import ValidationError


@pytest.mark.parametrize(
    ("assumption", "expected"),
    [
        (Decimal("-0.20"), Decimal("80.0000")),
        (Decimal("-0.10"), Decimal("90.0000")),
        (Decimal("0.10"), Decimal("110.0000")),
        (Decimal("0.20"), Decimal("120.0000")),
    ],
)
def test_supported_assumptions_are_calculated_deterministically(
    assumption: Decimal, expected: Decimal
) -> None:
    result = calculate_referral_inflow_change(Decimal("100"), assumption)

    assert result.calculated_value == expected
    assert result.delta_absolute == expected - Decimal("100.0000")
    assert result.delta_percent == assumption


def test_calculation_uses_round_half_up_to_four_places() -> None:
    result = calculate_referral_inflow_change(Decimal("1.00005"), Decimal("0.10"))

    assert result.baseline_value == Decimal("1.0001")
    assert result.calculated_value == Decimal("1.1001")
    assert result.delta_absolute == Decimal("0.1000")


def test_unsupported_assumption_is_rejected() -> None:
    with pytest.raises(ValidationError, match="допущение"):
        calculate_referral_inflow_change(Decimal("100"), Decimal("0.15"))


def test_non_positive_baseline_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Baseline"):
        calculate_referral_inflow_change(Decimal("0"), Decimal("0.10"))
