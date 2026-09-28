"""Framework-free contracts exchanged by Signal Engine evaluators."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from app.models.enums import (
    DataScopeType,
    SignalSeverity,
    SignalSourceType,
    SignalType,
)
from app.shared.signal_engine import (
    DailyAggregate,
    ForecastEvidence,
    FreshnessEvidence,
    QualityMeasurement,
    TimeSeriesEvidence,
)


class EvaluationStatus(StrEnum):
    FIRED = "FIRED"
    NO_SIGNAL = "NO_SIGNAL"
    SUPPRESSED = "SUPPRESSED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    FAILED = "FAILED"


class PersistenceStatus(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CREATED = "CREATED"
    SKIP_IDEMPOTENT = "SKIP_IDEMPOTENT"


@dataclass(frozen=True, slots=True)
class SignalCandidate:
    signal_type: SignalType
    severity: SignalSeverity
    source_type: SignalSourceType
    title: str
    summary: str
    observed_at: datetime
    evaluation_period_start: date
    evaluation_period_end: date
    reference_period_start: date | None
    reference_period_end: date | None
    actual_value: float
    baseline_value: float | None
    delta_absolute: float | None
    delta_percent: float | None
    rule_code: str
    rule_version: str
    rule_config: dict[str, Any]
    source: str
    data_watermark: dict[str, Any]
    data_current: bool
    evidence: dict[str, Any]
    caveats: tuple[str, ...] = ()
    scope_type: DataScopeType = DataScopeType.GLOBAL
    scope_id: uuid.UUID | None = None
    forecast_id: uuid.UUID | None = None
    model_version: str | None = None

    @property
    def dedup_key(self) -> str:
        identity = {
            "signal_type": self.signal_type.value,
            "scope_type": self.scope_type.value,
            "scope_id": str(self.scope_id) if self.scope_id else None,
            "evaluation_period_start": self.evaluation_period_start.isoformat(),
            "evaluation_period_end": self.evaluation_period_end.isoformat(),
            "rule_code": self.rule_code,
            "rule_version": self.rule_version,
            "data_watermark": self.data_watermark,
        }
        payload = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class EvaluatorResult:
    evaluator: str
    status: EvaluationStatus
    candidate: SignalCandidate | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    evaluator: str
    dataset_type: str | None
    status: EvaluationStatus
    reason: str | None
    persistence: PersistenceStatus = PersistenceStatus.NOT_APPLICABLE
    signal_id: uuid.UUID | None = None
    dedup_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SignalEvaluationReport:
    generated_at: datetime
    records: tuple[EvaluationRecord, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "records": [
                {
                    "evaluator": item.evaluator,
                    "dataset_type": item.dataset_type,
                    "status": item.status.value,
                    "reason": item.reason,
                    "persistence": item.persistence.value,
                    "signal_id": str(item.signal_id) if item.signal_id else None,
                    "dedup_key": item.dedup_key,
                    "metadata": item.metadata,
                }
                for item in self.records
            ],
        }


__all__ = [
    "DailyAggregate",
    "EvaluationRecord",
    "EvaluationStatus",
    "EvaluatorResult",
    "ForecastEvidence",
    "FreshnessEvidence",
    "PersistenceStatus",
    "QualityMeasurement",
    "SignalCandidate",
    "SignalEvaluationReport",
    "TimeSeriesEvidence",
]
