"""Signal Engine orchestration and idempotent candidate persistence."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.business.ports import UnitOfWorkFactory
from app.business.signals.contracts import (
    EvaluationRecord,
    EvaluationStatus,
    EvaluatorResult,
    PersistenceStatus,
    SignalCandidate,
    SignalEvaluationReport,
)
from app.business.signals.evaluators import (
    DataQualityEvaluator,
    DataStaleEvaluator,
    ForecastGrowthEvaluator,
    ReferralSpikeEvaluator,
    RefusalSpikeEvaluator,
)
from app.business.signals.policy import SignalPolicy
from app.business.signals.ports import SignalInputRepository
from app.core.logging import get_logger
from app.core.request_context import get_request_id
from app.models.enums import (
    AuditAction,
    AuditEntityType,
    DataScopeType,
    ExplanationGenerator,
    SignalSourceType,
    SignalStatus,
)
from app.models.signal import Signal, SignalExplanation

logger = get_logger(__name__)


class SignalEvaluationService:
    """Run independent evaluators, then persist only fired candidates."""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        inputs: SignalInputRepository,
        policy: SignalPolicy,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._inputs = inputs
        self._policy = policy
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._stale = DataStaleEvaluator(policy)
        self._quality = DataQualityEvaluator(policy)
        self._referrals = ReferralSpikeEvaluator(policy)
        self._refusals = RefusalSpikeEvaluator(policy)
        self._forecast = ForecastGrowthEvaluator(policy)

    def evaluate_all(self) -> SignalEvaluationReport:
        now = self._clock()
        results: list[tuple[str | None, EvaluatorResult]] = []
        current_by_dataset: dict[str, bool] = {}

        try:
            freshness = self._inputs.freshness_evidence()
            for evidence in freshness:
                result = self._stale.evaluate(evidence, now=now)
                results.append((evidence.dataset_type, result))
                current_by_dataset[evidence.dataset_type] = (
                    result.status is EvaluationStatus.NO_SIGNAL
                )
        except Exception as exc:  # evaluator isolation boundary
            logger.error("Не удалось оценить актуальность данных", exc_info=exc)
            results.append(
                (
                    None,
                    EvaluatorResult(
                        "DATA_STALE", EvaluationStatus.FAILED, reason="INPUT_FAILURE"
                    ),
                )
            )

        try:
            for measurement in self._inputs.quality_measurements():
                results.append(
                    (
                        measurement.dataset_type,
                        self._quality.evaluate(measurement, now=now),
                    )
                )
        except Exception as exc:  # evaluator isolation boundary
            logger.error("Не удалось оценить качество данных", exc_info=exc)
            results.append(
                (
                    None,
                    EvaluatorResult(
                        "DATA_QUALITY_DEGRADED",
                        EvaluationStatus.FAILED,
                        reason="INPUT_FAILURE",
                    ),
                )
            )

        required_days = self._policy.spike_window_days * (
            self._policy.spike_reference_windows + 1
        )
        for dataset_type, evaluator in (
            ("REFERRALS", self._referrals),
            ("REFUSALS", self._refusals),
        ):
            try:
                if dataset_type not in current_by_dataset:
                    result = EvaluatorResult(
                        evaluator.name,
                        EvaluationStatus.INSUFFICIENT_DATA,
                        reason="FRESHNESS_EVIDENCE_NOT_AVAILABLE",
                    )
                else:
                    time_series = self._inputs.daily_evidence(
                        dataset_type,
                        before=now.date(),
                        source_is_current=current_by_dataset[dataset_type],
                        limit_days=required_days,
                    )
                    result = evaluator.evaluate(time_series, now=now)
                results.append((dataset_type, result))
            except Exception as exc:  # evaluator isolation boundary
                logger.error(
                    "Не удалось оценить статистический сигнал",
                    extra={"dataset_type": dataset_type},
                    exc_info=exc,
                )
                results.append(
                    (
                        dataset_type,
                        EvaluatorResult(
                            evaluator.name,
                            EvaluationStatus.FAILED,
                            reason="INPUT_FAILURE",
                        ),
                    )
                )

        try:
            forecast = self._inputs.latest_forecast(now=now)
            results.append((None, self._forecast.evaluate(forecast, now=now)))
        except Exception as exc:  # evaluator isolation boundary
            logger.error("Не удалось оценить прогнозный сигнал", exc_info=exc)
            results.append(
                (
                    None,
                    EvaluatorResult(
                        self._forecast.name,
                        EvaluationStatus.FAILED,
                        reason="INPUT_FAILURE",
                    ),
                )
            )

        records = tuple(
            self._record(dataset_type, result) for dataset_type, result in results
        )
        return SignalEvaluationReport(generated_at=now, records=records)

    def _record(
        self, dataset_type: str | None, result: EvaluatorResult
    ) -> EvaluationRecord:
        if result.candidate is None:
            return EvaluationRecord(
                evaluator=result.evaluator,
                dataset_type=dataset_type,
                status=result.status,
                reason=result.reason,
                metadata=dict(result.metadata),
            )
        signal_id, persistence = self._persist_candidate(result.candidate)
        return EvaluationRecord(
            evaluator=result.evaluator,
            dataset_type=dataset_type,
            status=result.status,
            reason=result.reason,
            persistence=persistence,
            signal_id=signal_id,
            dedup_key=result.candidate.dedup_key,
            metadata={"rule_code": result.candidate.rule_code},
        )

    def _persist_candidate(
        self, candidate: SignalCandidate
    ) -> tuple[uuid.UUID, PersistenceStatus]:
        with self._uow_factory() as uow:
            existing = uow.signals.find_by_dedup_key(candidate.dedup_key)
            if existing is not None:
                return existing.id, PersistenceStatus.SKIP_IDEMPOTENT

            signal = self._to_signal(candidate)
            persisted, created = uow.signals.add_if_absent(signal)
            if not created:
                return persisted.id, PersistenceStatus.SKIP_IDEMPOTENT
            uow.audit.append(
                actor_user_id=None,
                action=AuditAction.SIGNAL_CREATED,
                entity_type=AuditEntityType.SIGNAL,
                entity_id=signal.id,
                request_id=get_request_id(),
                metadata={
                    "signal_type": candidate.signal_type.value,
                    "scope_type": candidate.scope_type.value,
                    "rule_code": candidate.rule_code,
                    "rule_version": candidate.rule_version,
                    "dedup_key": candidate.dedup_key,
                },
            )
            uow.commit()
        return persisted.id, PersistenceStatus.CREATED

    @staticmethod
    def _to_signal(candidate: SignalCandidate) -> Signal:
        region_id = (
            candidate.scope_id if candidate.scope_type is DataScopeType.REGION else None
        )
        hospital_id = (
            candidate.scope_id if candidate.scope_type is DataScopeType.HOSPITAL else None
        )
        generator = (
            ExplanationGenerator.RULE_ENGINE
            if candidate.source_type is SignalSourceType.RULE_BASED
            else ExplanationGenerator.STATISTICAL
        )
        signal = Signal(
            id=uuid.uuid4(),
            scope_type=candidate.scope_type,
            region_id=region_id,
            hospital_id=hospital_id,
            type=candidate.signal_type,
            severity=candidate.severity,
            status=SignalStatus.NEW,
            source_type=candidate.source_type,
            title=candidate.title,
            summary=candidate.summary,
            detected_at=candidate.observed_at,
            evaluation_period_start=candidate.evaluation_period_start,
            evaluation_period_end=candidate.evaluation_period_end,
            reference_period_start=candidate.reference_period_start,
            reference_period_end=candidate.reference_period_end,
            actual_value=candidate.actual_value,
            baseline_value=candidate.baseline_value,
            delta_absolute=candidate.delta_absolute,
            delta_percent=candidate.delta_percent,
            rule_code=candidate.rule_code,
            rule_version=candidate.rule_version,
            rule_config=dict(candidate.rule_config),
            evidence=dict(candidate.evidence),
            source=candidate.source,
            data_watermark=dict(candidate.data_watermark),
            data_current=candidate.data_current,
            dedup_key=candidate.dedup_key,
            forecast_id=candidate.forecast_id,
            version=1,
        )
        signal.explanation = SignalExplanation(
            signal_id=signal.id,
            summary=candidate.summary,
            factors=[
                {
                    "rule_code": candidate.rule_code,
                    "actual_value": candidate.actual_value,
                    "baseline_value": candidate.baseline_value,
                    "delta_absolute": candidate.delta_absolute,
                    "delta_percent": candidate.delta_percent,
                }
            ],
            caveats=list(candidate.caveats),
            generator=generator,
            generator_version=f"{candidate.rule_code}:{candidate.rule_version}",
            model_version=candidate.model_version,
            input_period_start=datetime.combine(
                candidate.evaluation_period_start, datetime.min.time(), tzinfo=UTC
            ),
            input_period_end=datetime.combine(
                candidate.evaluation_period_end, datetime.max.time(), tzinfo=UTC
            ),
            generated_at=candidate.observed_at,
        )
        return signal
