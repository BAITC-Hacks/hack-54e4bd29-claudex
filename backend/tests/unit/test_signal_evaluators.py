from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.business.signals.contracts import (
    DailyAggregate,
    EvaluationStatus,
    ForecastEvidence,
    FreshnessEvidence,
    QualityMeasurement,
    TimeSeriesEvidence,
)
from app.business.signals.evaluators import (
    DataQualityEvaluator,
    DataStaleEvaluator,
    ForecastGrowthEvaluator,
    ReferralSpikeEvaluator,
    RefusalSpikeEvaluator,
)
from app.business.signals.policy import SignalPolicy
from app.models.enums import SignalSeverity, SignalSourceType, SignalType

NOW = datetime(2025, 4, 1, 12, tzinfo=UTC)
WATERMARK = {"import_ids": ["import-1"], "completed_at": "2025-04-01T00:00:00Z"}


def _policy() -> SignalPolicy:
    return SignalPolicy()


def _series(*, latest_value: int = 100, current: bool = True) -> TimeSeriesEvidence:
    start = date(2025, 1, 1)
    points = tuple(
        DailyAggregate(
            observed_on=start + timedelta(days=index),
            value=latest_value if index >= 56 else 50,
            is_complete=True,
        )
        for index in range(63)
    )
    return TimeSeriesEvidence(
        dataset_type="REFERRALS",
        source="ИС БГ",
        points=points,
        watermark=WATERMARK,
        source_is_current=current,
    )


def test_data_stale_does_not_fire_at_exact_boundary() -> None:
    evidence = FreshnessEvidence(
        dataset_type="REFERRALS",
        source="ИС БГ",
        latest_successful_at=NOW - timedelta(hours=72),
        watermark=WATERMARK,
    )

    result = DataStaleEvaluator(_policy()).evaluate(evidence, now=NOW)

    assert result.status is EvaluationStatus.NO_SIGNAL


@pytest.mark.parametrize(
    ("age_hours", "severity"),
    [
        (73, SignalSeverity.WARNING),
        (144, SignalSeverity.HIGH),
        (288, SignalSeverity.CRITICAL),
    ],
)
def test_data_stale_severity_uses_configured_multipliers(
    age_hours: int, severity: SignalSeverity
) -> None:
    evidence = FreshnessEvidence(
        dataset_type="REFERRALS",
        source="ИС БГ",
        latest_successful_at=NOW - timedelta(hours=age_hours),
        watermark=WATERMARK,
    )

    result = DataStaleEvaluator(_policy()).evaluate(evidence, now=NOW)

    assert result.status is EvaluationStatus.FIRED
    assert result.candidate is not None
    assert result.candidate.signal_type is SignalType.DATA_STALE
    assert result.candidate.severity is severity
    assert result.candidate.rule_config["max_age_hours"] == 72


def test_data_stale_is_disabled_for_treated_without_delivery_semantics() -> None:
    evidence = FreshnessEvidence(
        dataset_type="TREATED",
        source="ЭРСБ",
        latest_successful_at=NOW - timedelta(days=500),
        watermark=WATERMARK,
    )

    result = DataStaleEvaluator(_policy()).evaluate(evidence, now=NOW)

    assert result.status is EvaluationStatus.INSUFFICIENT_DATA
    assert result.reason == "FRESHNESS_POLICY_NOT_CONFIGURED"


def test_quality_requires_a_formalized_denominator() -> None:
    measurement = QualityMeasurement(
        dataset_type="REFERRALS",
        source="ИС БГ",
        rule_code="HOSPITALIZATION_BEFORE_REGISTRATION",
        affected_rows=104_644,
        eligible_rows=None,
        denominator_code=None,
        watermark=WATERMARK,
    )

    result = DataQualityEvaluator(_policy()).evaluate(measurement, now=NOW)

    assert result.status is EvaluationStatus.INSUFFICIENT_DATA
    assert result.reason == "FORMAL_DENOMINATOR_NOT_AVAILABLE"
    assert result.metadata == {
        "rule_code": "HOSPITALIZATION_BEFORE_REGISTRATION",
        "affected_rows": 104_644,
        "eligible_rows": None,
        "denominator_code": None,
    }


@pytest.mark.parametrize(
    ("affected", "severity"),
    [
        (10, SignalSeverity.WARNING),
        (50, SignalSeverity.HIGH),
        (100, SignalSeverity.CRITICAL),
    ],
)
def test_quality_uses_affected_over_explicit_eligible_rows(
    affected: int, severity: SignalSeverity
) -> None:
    measurement = QualityMeasurement(
        dataset_type="REFERRALS",
        source="ИС БГ",
        rule_code="FORMAL_RULE",
        affected_rows=affected,
        eligible_rows=1_000,
        denominator_code="ELIGIBLE_ROWS_WITH_BOTH_DATES",
        watermark=WATERMARK,
    )

    result = DataQualityEvaluator(_policy()).evaluate(measurement, now=NOW)

    assert result.status is EvaluationStatus.FIRED
    assert result.candidate is not None
    assert result.candidate.signal_type is SignalType.DATA_QUALITY_DEGRADED
    assert result.candidate.severity is severity
    assert result.candidate.actual_value == pytest.approx(affected / 10)


def test_referral_spike_uses_eight_strictly_prior_non_overlapping_windows() -> None:
    result = ReferralSpikeEvaluator(_policy()).evaluate(_series(), now=NOW)

    assert result.status is EvaluationStatus.FIRED
    assert result.candidate is not None
    candidate = result.candidate
    assert candidate.signal_type is SignalType.REFERRAL_SPIKE
    assert candidate.actual_value == 700
    assert candidate.baseline_value == 350
    assert candidate.delta_percent == 100
    assert candidate.reference_period_end < candidate.evaluation_period_start
    assert candidate.rule_config["reference_windows"] == 8
    assert candidate.rule_config["window_days"] == 7


def test_referral_spike_excludes_latest_partial_day() -> None:
    evidence = _series()
    points = (*evidence.points, DailyAggregate(date(2025, 3, 5), 999_999, False))

    result = ReferralSpikeEvaluator(_policy()).evaluate(
        TimeSeriesEvidence(
            dataset_type=evidence.dataset_type,
            source=evidence.source,
            points=points,
            watermark=evidence.watermark,
            source_is_current=True,
        ),
        now=NOW,
    )

    assert result.status is EvaluationStatus.FIRED
    assert result.candidate is not None
    assert result.candidate.actual_value == 700
    assert result.candidate.evaluation_period_end == date(2025, 3, 4)


def test_referral_spike_returns_no_signal_for_normal_series() -> None:
    result = ReferralSpikeEvaluator(_policy()).evaluate(_series(latest_value=55), now=NOW)

    assert result.status is EvaluationStatus.NO_SIGNAL


def test_referral_spike_is_suppressed_when_source_is_stale() -> None:
    result = ReferralSpikeEvaluator(_policy()).evaluate(_series(current=False), now=NOW)

    assert result.status is EvaluationStatus.SUPPRESSED
    assert result.reason == "SOURCE_DATA_STALE"


def test_referral_spike_requires_all_consecutive_complete_days() -> None:
    evidence = _series()
    result = ReferralSpikeEvaluator(_policy()).evaluate(
        TimeSeriesEvidence(
            dataset_type=evidence.dataset_type,
            source=evidence.source,
            points=evidence.points[:-1],
            watermark=evidence.watermark,
            source_is_current=True,
        ),
        now=NOW,
    )

    assert result.status is EvaluationStatus.INSUFFICIENT_DATA
    assert result.reason == "INSUFFICIENT_COMPLETE_HISTORY"


def test_refusal_spike_uses_refusal_signal_type() -> None:
    evidence = _series()
    result = RefusalSpikeEvaluator(_policy()).evaluate(
        TimeSeriesEvidence(
            dataset_type="REFUSALS",
            source=evidence.source,
            points=evidence.points,
            watermark=evidence.watermark,
            source_is_current=True,
        ),
        now=NOW,
    )

    assert result.status is EvaluationStatus.FIRED
    assert result.candidate is not None
    assert result.candidate.signal_type is SignalType.REFUSAL_SPIKE


def _forecast(*, freshness: str, predicted: float, baseline: float) -> ForecastEvidence:
    return ForecastEvidence(
        forecast_id=uuid.UUID("00000000-0000-0000-0000-000000000123"),
        source="ИС БГ",
        freshness_status=freshness,
        status="VALID",
        horizon_start=date(2025, 4, 2),
        horizon_end=date(2025, 4, 8),
        forecast_value=predicted,
        baseline_value=baseline,
        selected_model="weekly_naive",
        selected_model_type="BASELINE",
        model_version="referrals-global-v1",
        generated_at=NOW,
        watermark=WATERMARK,
    )


def test_forecast_growth_fires_for_current_valid_baseline_forecast() -> None:
    result = ForecastGrowthEvaluator(_policy()).evaluate(
        _forecast(freshness="CURRENT", predicted=1_300, baseline=1_000), now=NOW
    )

    assert result.status is EvaluationStatus.FIRED
    assert result.candidate is not None
    assert result.candidate.signal_type is SignalType.FORECAST_INFLOW_GROWTH
    assert result.candidate.source_type is SignalSourceType.STATISTICAL
    assert result.candidate.model_version == "referrals-global-v1"


def test_forecast_growth_is_suppressed_for_stale_forecast() -> None:
    result = ForecastGrowthEvaluator(_policy()).evaluate(
        _forecast(freshness="STALE", predicted=2_000, baseline=1_000), now=NOW
    )

    assert result.status is EvaluationStatus.SUPPRESSED
    assert result.reason == "FORECAST_STALE"


def test_forecast_growth_returns_no_signal_below_threshold() -> None:
    result = ForecastGrowthEvaluator(_policy()).evaluate(
        _forecast(freshness="CURRENT", predicted=1_199, baseline=1_000), now=NOW
    )

    assert result.status is EvaluationStatus.NO_SIGNAL


def test_candidate_dedup_key_is_deterministic_and_changes_with_watermark() -> None:
    first = ReferralSpikeEvaluator(_policy()).evaluate(_series(), now=NOW).candidate
    second = ReferralSpikeEvaluator(_policy()).evaluate(_series(), now=NOW).candidate
    assert first is not None and second is not None
    assert first.dedup_key == second.dedup_key

    changed_evidence = _series()
    changed = (
        ReferralSpikeEvaluator(_policy())
        .evaluate(
            TimeSeriesEvidence(
                dataset_type=changed_evidence.dataset_type,
                source=changed_evidence.source,
                points=changed_evidence.points,
                watermark={"import_ids": ["import-2"]},
                source_is_current=True,
            ),
            now=NOW,
        )
        .candidate
    )
    assert changed is not None
    assert changed.dedup_key != first.dedup_key
