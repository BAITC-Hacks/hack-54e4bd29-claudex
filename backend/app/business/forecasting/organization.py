"""Organization inference gates and atomic persistence through existing entities."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.business.forecasting.contracts import (
    OrganizationForecastInput,
    OrganizationForecastRequest,
)
from app.business.forecasting.ports import (
    OrganizationForecastRepository,
    OrganizationModelEngine,
)
from app.business.signals.evaluation import SignalEvaluationService
from app.business.signals.evaluators import ForecastGrowthEvaluator
from app.business.signals.policy import SignalPolicy
from app.models.analytics import Forecast
from app.models.enums import DataScopeType, ForecastStatus, ModelVersionStatus
from app.models.forecast_point import ForecastPoint
from app.shared.forecasting import REFERRAL_TARGET
from app.shared.signal_engine import ForecastEvidence


class OrganizationForecastService:
    def __init__(
        self,
        *,
        enabled: bool = False,
        repository: OrganizationForecastRepository | None = None,
        engine: OrganizationModelEngine | None = None,
        policy: SignalPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._enabled = enabled
        self._repository = repository
        self._engine = engine
        self._policy = policy or SignalPolicy()
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def operation_id(request: OrganizationForecastRequest) -> uuid.UUID:
        identity = [
            "organization-forecast-v1",
            str(request.hospital_id),
            REFERRAL_TARGET,
            request.origin.isoformat(),
            request.horizon_days,
            request.model_version,
            request.mapping_version,
            request.delivery_watermark,
        ]
        digest = hashlib.sha256(
            json.dumps(identity, separators=(",", ":")).encode()
        ).hexdigest()
        return uuid.uuid5(uuid.NAMESPACE_URL, digest)

    def run(self, request: OrganizationForecastRequest) -> dict[str, object]:
        if not self._enabled:
            return {"status": "SUPPRESSED", "reason": "ORGANIZATION_FORECAST_DISABLED"}
        if self._repository is None or self._engine is None:
            return {
                "status": "SUPPRESSED",
                "reason": "ORGANIZATION_CONTRACT_NOT_CONFIGURED",
            }
        operation_id = self.operation_id(request)
        with self._repository.transaction(operation_id) as tx:
            cached = tx.terminal_result()
            if cached is not None:
                return cached

            def suppress(reason: str) -> dict[str, object]:
                return tx.finish(
                    {
                        "operation_id": str(operation_id),
                        "status": "SUPPRESSED",
                        "reason": reason,
                    }
                )

            now = self._clock()
            if request.origin < now.date():
                return suppress("FORECAST_STALE")
            if request.origin != now.date() or request.horizon_days != 7:
                return suppress("UNSUPPORTED_FORECAST_WINDOW")
            history = tx.locked_input(request)
            if history is None:
                return suppress("APPROVED_INPUT_NOT_AVAILABLE")
            reason = self._input_reason(request, history, self._clock())
            if reason:
                return suppress(reason)
            model = tx.registered_model(request.model_version)
            if model is None or model.status != ModelVersionStatus.SELECTED:
                return suppress("MODEL_NOT_REGISTERED")
            if (
                model.target != REFERRAL_TARGET
                or model.forecast_horizon_days != request.horizon_days
            ):
                return suppress("MODEL_SCOPE_MISMATCH")
            registry = model.validation_config.get("organization_forecast_v1", {})
            if registry.get("model_type") != "ML":
                return suppress("UNSUPPORTED_MODEL_TYPE")
            try:
                admission = self._engine.admission(model, history)
            except (ValueError, TypeError, KeyError):
                return suppress("INVALID_ADMISSION_EVIDENCE")
            if admission.get("status") != "PASS":
                status = admission.get("status")
                return suppress(
                    status
                    if isinstance(status, str)
                    and status in {"POLICY_NOT_APPROVED", "INSUFFICIENT_DATA", "FAIL"}
                    else "UNSUPPORTED_ADMISSION_STATUS"
                )
            try:
                result = self._engine.predict(model, history)
            except ValueError:
                return suppress("INVALID_MODEL_OUTPUT")
            context = result.organization_evidence
            expected_policy = {
                "version": "referral-growth-v1",
                "window_days": 7,
                "reference_days": 28,
                "min_reference_total": 20,
                "min_extra_referrals": 10,
                "growth_threshold_percent": 20,
            }
            if (
                not isinstance(context, dict)
                or context.get("schema_version") != "organization-alert-policy-v1"
                or context.get("episode_policy") != expected_policy
                or context.get("protocol_sha256") != registry.get("protocol_sha256")
                or self._policy.warning_percent != 20
            ):
                return suppress("MODEL_POLICY_MISMATCH")
            anchor_value = context.get("episode_anchor")
            try:
                if not isinstance(anchor_value, str):
                    raise ValueError("Missing episode anchor")
                anchor = date.fromisoformat(anchor_value)
            except ValueError:
                return suppress("MODEL_POLICY_MISMATCH")
            aligned = request.origin >= anchor and (request.origin - anchor).days % 7 == 0
            expected_dates = tuple(
                request.origin + timedelta(days=i) for i in range(request.horizon_days)
            )
            numbers: list[Any] = [
                v
                for point in result.points
                for v in (point.predicted_value, point.baseline_value)
            ]
            metrics = [
                result.metrics.as_dict(),
                result.baseline_metrics.as_dict(),
                model.metrics,
                model.baseline_metrics,
            ]
            for metric in metrics:
                numbers.extend(metric.get(key) for key in ("mae", "rmse"))
                if metric.get("wape") is not None:
                    numbers.append(metric["wape"])
            if (
                tuple(p.forecast_date for p in result.points) != expected_dates
                or any(
                    type(v) not in (int, float)
                    or not math.isfinite(v)
                    or not 0 <= v < 1e12
                    for v in numbers
                )
                or result.model_version != model.version
                or result.selected_model_type != "ML"
                or result.selected_model != model.algorithm
                or result.feature_schema_version != model.feature_schema_version
                or result.input_period_start != history.history[0].observed_on
                or result.input_period_end != history.history[-1].observed_on
                or result.generated_at.tzinfo is None
                or result.generated_at.date() != request.origin
            ):
                return suppress("INVALID_MODEL_OUTPUT")
            total_baseline = sum(p.baseline_value for p in result.points)
            total_prediction = sum(p.predicted_value for p in result.points)
            if (
                total_baseline > 0
                and not abs((total_prediction / total_baseline - 1) * 100) < 1e8
            ):
                return suppress("INVALID_MODEL_OUTPUT")
            # Publication locks remain held; recheck protects adapters and future changes.
            if not tx.recheck(request):
                return suppress("PUBLICATION_CHANGED")
            if self._clock().date() != request.origin:
                return suppress("FORECAST_STALE")
            raw_policy = admission.get("policy_snapshot")
            if not isinstance(raw_policy, dict):
                return suppress("INVALID_ADMISSION_EVIDENCE")
            policy_snapshot = dict(raw_policy)
            # Preserve policy values without private review references.
            sign_off = policy_snapshot.pop("sign_off", {}) or {}
            public_admission = {
                "status": "PASS",
                "reason_codes": [],
                "policy_snapshot": policy_snapshot,
                "policy_sha256": sign_off.get("policy_sha256"),
            }
            input_rows = [[p.observed_on.isoformat(), p.count] for p in history.history]
            input_digest = hashlib.sha256(
                json.dumps(input_rows, separators=(",", ":")).encode()
            ).hexdigest()
            watermark = {
                "schema_version": "organization-forecast-v1",
                "mapping_version": history.mapping_version,
                "delivery_watermark": history.delivery_watermark,
                "model_version": model.version,
                "artifact_sha256": registry["artifact_sha256"],
                "protocol_sha256": registry["protocol_sha256"],
                "code_sha256": registry["code_sha256"],
                "hospital_id": str(request.hospital_id),
                "origin": request.origin.isoformat(),
                "horizon_days": request.horizon_days,
                "input_sha256": input_digest,
                "admission": public_admission,
                "alert_policy": dict(context),
            }
            forecast = Forecast(
                id=uuid.uuid5(operation_id, "forecast"),
                hospital_id=request.hospital_id,
                region_id=None,
                scope_type=DataScopeType.HOSPITAL,
                target=REFERRAL_TARGET,
                horizon_days=request.horizon_days,
                predicted_value=sum(p.predicted_value for p in result.points),
                model_version=model.version,
                model_version_id=model.id,
                metric_name="MAE",
                metric_value=model.metrics["mae"],
                baseline_metric_name="MAE",
                baseline_metric_value=model.baseline_metrics["mae"],
                input_period_start=datetime.combine(
                    result.input_period_start, datetime.min.time(), UTC
                ),
                input_period_end=datetime.combine(
                    result.input_period_end, datetime.max.time(), UTC
                ),
                generated_at=now,
                status=ForecastStatus.VALID,
                assumptions=["Расчётный прогноз потока; решение принимает сотрудник."],
                selected_model=model.algorithm,
                baseline_model=result.strongest_baseline,
                feature_schema_version=model.feature_schema_version,
                dataset_watermark=watermark,
                validation_metrics=dict(model.metrics),
                baseline_metrics=dict(model.baseline_metrics),
                validation_folds=list(result.validation_folds),
                forecast_start=expected_dates[0],
                forecast_end=expected_dates[-1],
            )
            points = tuple(
                ForecastPoint(
                    forecast_id=forecast.id,
                    forecast_date=p.forecast_date,
                    predicted_value=p.predicted_value,
                    baseline_value=p.baseline_value,
                )
                for p in result.points
            )
            evidence = ForecastEvidence(
                forecast_id=forecast.id,
                source="ИС БГ",
                freshness_status="CURRENT",
                status="VALID",
                horizon_start=expected_dates[0],
                horizon_end=expected_dates[-1],
                forecast_value=forecast.predicted_value,
                baseline_value=sum(p.count for p in history.history[-28:]) / 4,
                selected_model=model.algorithm,
                selected_model_type=registry["model_type"],
                model_version=model.version,
                generated_at=now,
                watermark=watermark,
            )
            evaluated = ForecastGrowthEvaluator(self._policy).evaluate(
                evidence, now=now, admitted_organization=True
            )
            signal = None
            if aligned and evaluated.candidate is not None:
                candidate = replace(
                    evaluated.candidate,
                    scope_type=DataScopeType.HOSPITAL,
                    scope_id=request.hospital_id,
                    rule_version="org-growth-v1",
                    rule_config={
                        **evaluated.candidate.rule_config,
                        **context,
                        "cadence_days": 7,
                        "reference_method": "prior_28_days_total_divided_by_4",
                        "severity_policy_version": self._policy.rule_version,
                    },
                    reference_period_start=request.origin - timedelta(days=28),
                    reference_period_end=request.origin - timedelta(days=1),
                    title="Прогнозируемый поток выше недельного уровня за 28 дней",
                    summary=(
                        "Прогноз превышает средний недельный поток за предыдущие "
                        "28 дней. Это прогнозное предупреждение, "
                        "а не подтверждение перегрузки."
                    ),
                    evidence={
                        **evaluated.candidate.evidence,
                        "forecast_baseline_value": total_baseline,
                        "reference_weekly_value": evidence.baseline_value,
                    },
                )
                signal = SignalEvaluationService._to_signal(candidate)
                # One operational episode across model/watermark retries and revisions.
                signal.id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"organization-growth-v1:{request.hospital_id}:{request.origin.isoformat()}",
                )
                if signal.explanation is not None:
                    signal.explanation.signal_id = signal.id
            return tx.finish(
                {
                    "operation_id": str(operation_id),
                    "status": "COMPLETED",
                    "forecast_id": str(forecast.id),
                    "signal_id": str(signal.id) if signal else None,
                },
                forecast=forecast,
                points=points,
                signal=signal,
            )

    def _input_reason(
        self,
        request: OrganizationForecastRequest,
        history: OrganizationForecastInput,
        now: datetime,
    ) -> str | None:
        if (
            history.hospital_id != request.hospital_id
            or history.mapping_version != request.mapping_version
            or history.delivery_watermark != request.delivery_watermark
        ):
            return "SCOPE_EVIDENCE_MISMATCH"
        if not history.coverage_complete:
            return "DELIVERY_INCOMPLETE"
        max_age = self._policy.freshness_max_age_hours["REFERRALS"]
        if (
            history.as_of.tzinfo is None
            or history.as_of > now
            or max_age is None
            or (now - history.as_of).total_seconds() > max_age * 3600
        ):
            return "SOURCE_DATA_STALE"
        if len(history.history) < 42:
            return "INSUFFICIENT_HISTORY"
        if history.history[-1].observed_on != request.origin - timedelta(days=1):
            return "HISTORY_NOT_CURRENT"
        if any(type(p.count) is not int or p.count < 0 for p in history.history):
            return "INVALID_HISTORY"
        if any(
            (b.observed_on - a.observed_on).days != 1
            for a, b in zip(history.history, history.history[1:], strict=False)
        ):
            return "INCOMPLETE_HISTORY"
        return None
