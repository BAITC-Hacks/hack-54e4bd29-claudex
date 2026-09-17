"""Pure deterministic Signal Engine rules.

Evaluators never write storage. They turn aggregate evidence into a candidate
or an explicit non-firing result that orchestration can report safely.
"""

from __future__ import annotations

from datetime import datetime
from itertools import pairwise
from statistics import median

from app.business.signals.contracts import (
    EvaluationStatus,
    EvaluatorResult,
    ForecastEvidence,
    FreshnessEvidence,
    QualityMeasurement,
    SignalCandidate,
    TimeSeriesEvidence,
)
from app.business.signals.policy import SignalPolicy
from app.models.enums import SignalSeverity, SignalSourceType, SignalType


def _growth_severity(percent: float, policy: SignalPolicy) -> SignalSeverity | None:
    if percent >= policy.critical_percent:
        return SignalSeverity.CRITICAL
    if percent >= policy.high_percent:
        return SignalSeverity.HIGH
    if percent >= policy.warning_percent:
        return SignalSeverity.WARNING
    return None


def _quality_severity(percent: float, policy: SignalPolicy) -> SignalSeverity | None:
    if percent >= policy.quality_critical_percent:
        return SignalSeverity.CRITICAL
    if percent >= policy.quality_high_percent:
        return SignalSeverity.HIGH
    if percent >= policy.quality_warning_percent:
        return SignalSeverity.WARNING
    return None


class DataStaleEvaluator:
    name = "DATA_STALE"

    def __init__(self, policy: SignalPolicy) -> None:
        self._policy = policy

    def evaluate(self, evidence: FreshnessEvidence, *, now: datetime) -> EvaluatorResult:
        max_age = self._policy.freshness_max_age_hours.get(evidence.dataset_type)
        if max_age is None:
            return EvaluatorResult(
                self.name,
                EvaluationStatus.INSUFFICIENT_DATA,
                reason="FRESHNESS_POLICY_NOT_CONFIGURED",
            )
        if evidence.latest_successful_at is None:
            return EvaluatorResult(
                self.name,
                EvaluationStatus.INSUFFICIENT_DATA,
                reason="LATEST_SUCCESSFUL_TIMESTAMP_MISSING",
            )
        age_hours = (now - evidence.latest_successful_at).total_seconds() / 3600
        if age_hours <= max_age:
            return EvaluatorResult(self.name, EvaluationStatus.NO_SIGNAL)
        multiplier = age_hours / max_age
        if multiplier >= self._policy.freshness_critical_multiplier:
            severity = SignalSeverity.CRITICAL
        elif multiplier >= self._policy.freshness_high_multiplier:
            severity = SignalSeverity.HIGH
        else:
            severity = SignalSeverity.WARNING
        rule_code = f"DATA_STALE_{evidence.dataset_type}"
        candidate = SignalCandidate(
            signal_type=SignalType.DATA_STALE,
            severity=severity,
            source_type=SignalSourceType.RULE_BASED,
            title=f"Данные {evidence.dataset_type} требуют проверки актуальности",
            summary=(
                "Данные не обновлялись в пределах настроенного аналитического окна. "
                "Это сигнал о поставке данных, а не о нагрузке стационара."
            ),
            observed_at=now,
            evaluation_period_start=evidence.latest_successful_at.date(),
            evaluation_period_end=now.date(),
            reference_period_start=None,
            reference_period_end=None,
            actual_value=age_hours,
            baseline_value=float(max_age),
            delta_absolute=age_hours - max_age,
            delta_percent=(age_hours / max_age - 1) * 100,
            rule_code=rule_code,
            rule_version=self._policy.rule_version,
            rule_config={
                "max_age_hours": max_age,
                "high_multiplier": self._policy.freshness_high_multiplier,
                "critical_multiplier": self._policy.freshness_critical_multiplier,
            },
            source=evidence.source,
            data_watermark=evidence.watermark,
            data_current=False,
            evidence={
                "dataset_type": evidence.dataset_type,
                "latest_successful_at": evidence.latest_successful_at.isoformat(),
                "age_hours": age_hours,
                "expected_max_age_hours": max_age,
            },
            caveats=(
                "Порог является конфигурируемой аналитической политикой, а не SLA.",
            ),
        )
        return EvaluatorResult(self.name, EvaluationStatus.FIRED, candidate=candidate)


class DataQualityEvaluator:
    name = "DATA_QUALITY_DEGRADED"

    def __init__(self, policy: SignalPolicy) -> None:
        self._policy = policy

    def evaluate(self, evidence: QualityMeasurement, *, now: datetime) -> EvaluatorResult:
        if evidence.eligible_rows is None or evidence.denominator_code is None:
            return EvaluatorResult(
                self.name,
                EvaluationStatus.INSUFFICIENT_DATA,
                reason="FORMAL_DENOMINATOR_NOT_AVAILABLE",
                metadata={
                    "rule_code": evidence.rule_code,
                    "affected_rows": evidence.affected_rows,
                    "eligible_rows": evidence.eligible_rows,
                    "denominator_code": evidence.denominator_code,
                },
            )
        if evidence.eligible_rows <= 0 or evidence.affected_rows > evidence.eligible_rows:
            return EvaluatorResult(
                self.name,
                EvaluationStatus.INSUFFICIENT_DATA,
                reason="INVALID_QUALITY_DENOMINATOR",
                metadata={
                    "rule_code": evidence.rule_code,
                    "affected_rows": evidence.affected_rows,
                    "eligible_rows": evidence.eligible_rows,
                    "denominator_code": evidence.denominator_code,
                },
            )
        percent = evidence.affected_rows / evidence.eligible_rows * 100
        severity = _quality_severity(percent, self._policy)
        if severity is None:
            return EvaluatorResult(
                self.name,
                EvaluationStatus.NO_SIGNAL,
                metadata={
                    "rule_code": evidence.rule_code,
                    "affected_rows": evidence.affected_rows,
                    "eligible_rows": evidence.eligible_rows,
                    "denominator_code": evidence.denominator_code,
                    "affected_percent": percent,
                },
            )
        candidate = SignalCandidate(
            signal_type=SignalType.DATA_QUALITY_DEGRADED,
            severity=severity,
            source_type=SignalSourceType.RULE_BASED,
            title=f"Проверка качества данных {evidence.dataset_type}",
            summary=(
                f"Формализованное правило {evidence.rule_code} превысило "
                "настроенный порог качества данных."
            ),
            observed_at=now,
            evaluation_period_start=now.date(),
            evaluation_period_end=now.date(),
            reference_period_start=None,
            reference_period_end=None,
            actual_value=percent,
            baseline_value=self._policy.quality_warning_percent,
            delta_absolute=percent - self._policy.quality_warning_percent,
            delta_percent=None,
            rule_code=evidence.rule_code,
            rule_version=self._policy.rule_version,
            rule_config={
                "denominator_code": evidence.denominator_code,
                "warning_percent": self._policy.quality_warning_percent,
                "high_percent": self._policy.quality_high_percent,
                "critical_percent": self._policy.quality_critical_percent,
            },
            source=evidence.source,
            data_watermark=evidence.watermark,
            data_current=True,
            evidence={
                "dataset_type": evidence.dataset_type,
                "quality_rule": evidence.rule_code,
                "affected_rows": evidence.affected_rows,
                "eligible_rows": evidence.eligible_rows,
                "affected_percent": percent,
            },
            caveats=("Сигнал описывает качество данных, а не клиническую ситуацию.",),
        )
        return EvaluatorResult(self.name, EvaluationStatus.FIRED, candidate=candidate)


class _SpikeEvaluator:
    name = "SPIKE"
    signal_type: SignalType
    subject: str

    def __init__(self, policy: SignalPolicy) -> None:
        self._policy = policy

    def evaluate(self, evidence: TimeSeriesEvidence, *, now: datetime) -> EvaluatorResult:
        if not evidence.source_is_current:
            return EvaluatorResult(
                self.name,
                EvaluationStatus.SUPPRESSED,
                reason="SOURCE_DATA_STALE",
            )
        required = self._policy.spike_window_days * (
            self._policy.spike_reference_windows + 1
        )
        points = sorted(
            (point for point in evidence.points if point.is_complete),
            key=lambda point: point.observed_on,
        )
        if len(points) < required:
            return EvaluatorResult(
                self.name,
                EvaluationStatus.INSUFFICIENT_DATA,
                reason="INSUFFICIENT_COMPLETE_HISTORY",
            )
        selected = points[-required:]
        if any(
            (right.observed_on - left.observed_on).days != 1
            for left, right in pairwise(selected)
        ):
            return EvaluatorResult(
                self.name,
                EvaluationStatus.INSUFFICIENT_DATA,
                reason="NON_CONSECUTIVE_HISTORY",
            )
        window = self._policy.spike_window_days
        reference_points = selected[:-window]
        evaluation_points = selected[-window:]
        reference_totals = [
            sum(point.value for point in reference_points[index : index + window])
            for index in range(0, len(reference_points), window)
        ]
        baseline = float(median(reference_totals))
        if baseline <= 0:
            return EvaluatorResult(
                self.name,
                EvaluationStatus.INSUFFICIENT_DATA,
                reason="NON_POSITIVE_BASELINE",
            )
        actual = float(sum(point.value for point in evaluation_points))
        delta = actual - baseline
        delta_percent = delta / baseline * 100
        severity = _growth_severity(delta_percent, self._policy)
        if severity is None:
            return EvaluatorResult(self.name, EvaluationStatus.NO_SIGNAL)
        config = {
            "window_days": window,
            "reference_windows": self._policy.spike_reference_windows,
            "baseline_method": "MEDIAN_OF_NON_OVERLAPPING_WINDOWS",
            "warning_percent": self._policy.warning_percent,
            "high_percent": self._policy.high_percent,
            "critical_percent": self._policy.critical_percent,
            "complete_days_only": True,
        }
        candidate = SignalCandidate(
            signal_type=self.signal_type,
            severity=severity,
            source_type=SignalSourceType.STATISTICAL,
            title=f"Необычный рост: {self.subject}",
            summary=(
                f"Объём за {window} полных дней выше медианы восьми "
                "предыдущих непересекающихся окон. Это статистическое "
                "предупреждение, а не подтверждение перегрузки."
            ),
            observed_at=now,
            evaluation_period_start=evaluation_points[0].observed_on,
            evaluation_period_end=evaluation_points[-1].observed_on,
            reference_period_start=reference_points[0].observed_on,
            reference_period_end=reference_points[-1].observed_on,
            actual_value=actual,
            baseline_value=baseline,
            delta_absolute=delta,
            delta_percent=delta_percent,
            rule_code=self.name,
            rule_version=self._policy.rule_version,
            rule_config=config,
            source=evidence.source,
            data_watermark=evidence.watermark,
            data_current=True,
            evidence={
                "current_count": actual,
                "baseline_count": baseline,
                "absolute_difference": delta,
                "percentage_difference": delta_percent,
                "reference_window_totals": reference_totals,
            },
            caveats=("Сигнал не устанавливает факт перегрузки медицинской организации.",),
        )
        return EvaluatorResult(self.name, EvaluationStatus.FIRED, candidate=candidate)


class ReferralSpikeEvaluator(_SpikeEvaluator):
    name = "REFERRAL_SPIKE"
    signal_type = SignalType.REFERRAL_SPIKE
    subject = "направления"


class RefusalSpikeEvaluator(_SpikeEvaluator):
    name = "REFUSAL_SPIKE"
    signal_type = SignalType.REFUSAL_SPIKE
    subject = "отказы"


class ForecastGrowthEvaluator:
    name = "FORECAST_INFLOW_GROWTH"

    def __init__(self, policy: SignalPolicy) -> None:
        self._policy = policy

    def evaluate(
        self, evidence: ForecastEvidence | None, *, now: datetime
    ) -> EvaluatorResult:
        if evidence is None:
            return EvaluatorResult(
                self.name,
                EvaluationStatus.INSUFFICIENT_DATA,
                reason="FORECAST_NOT_AVAILABLE",
            )
        if evidence.status != "VALID":
            return EvaluatorResult(
                self.name,
                EvaluationStatus.SUPPRESSED,
                reason="FORECAST_NOT_VALID",
            )
        if evidence.freshness_status != "CURRENT":
            return EvaluatorResult(
                self.name,
                EvaluationStatus.SUPPRESSED,
                reason="FORECAST_STALE",
            )
        if evidence.baseline_value <= 0:
            return EvaluatorResult(
                self.name,
                EvaluationStatus.INSUFFICIENT_DATA,
                reason="NON_POSITIVE_FORECAST_BASELINE",
            )
        delta = evidence.forecast_value - evidence.baseline_value
        delta_percent = delta / evidence.baseline_value * 100
        severity = _growth_severity(delta_percent, self._policy)
        if severity is None:
            return EvaluatorResult(self.name, EvaluationStatus.NO_SIGNAL)
        source_type = (
            SignalSourceType.ML_BASED
            if evidence.selected_model_type.upper() == "ML"
            else SignalSourceType.STATISTICAL
        )
        candidate = SignalCandidate(
            signal_type=SignalType.FORECAST_INFLOW_GROWTH,
            severity=severity,
            source_type=source_type,
            title="Прогнозируемый входящий поток выше baseline",
            summary=(
                "Расчётный входящий поток выше baseline на том же горизонте. "
                "Это прогнозное предупреждение, а не подтверждение перегрузки."
            ),
            observed_at=now,
            evaluation_period_start=evidence.horizon_start,
            evaluation_period_end=evidence.horizon_end,
            reference_period_start=None,
            reference_period_end=None,
            actual_value=evidence.forecast_value,
            baseline_value=evidence.baseline_value,
            delta_absolute=delta,
            delta_percent=delta_percent,
            rule_code=self.name,
            rule_version=self._policy.rule_version,
            rule_config={
                "warning_percent": self._policy.warning_percent,
                "high_percent": self._policy.high_percent,
                "critical_percent": self._policy.critical_percent,
                "requires_current_valid_forecast": True,
            },
            source=evidence.source,
            data_watermark=evidence.watermark,
            data_current=True,
            evidence={
                "forecast_value": evidence.forecast_value,
                "baseline_value": evidence.baseline_value,
                "absolute_difference": delta,
                "percentage_difference": delta_percent,
                "selected_model": evidence.selected_model,
                "selected_model_type": evidence.selected_model_type,
                "forecast_generated_at": evidence.generated_at.isoformat(),
            },
            caveats=("Расчётный прогноз. Решение принимает уполномоченный сотрудник.",),
            forecast_id=evidence.forecast_id,
            model_version=evidence.model_version,
        )
        return EvaluatorResult(self.name, EvaluationStatus.FIRED, candidate=candidate)
