"""Synthetic organization integration gates; never imports/trains real datasets."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from threading import RLock
from uuid import UUID

import pytest

from app.business.forecasting.contracts import (
    DailyReferralCount,
    ForecastEngineResult,
    ForecastMetricSet,
    ForecastPointResult,
    OrganizationForecastInput,
    OrganizationForecastRequest,
)
from app.models.enums import DataScopeType, ModelVersionStatus
from app.models.model_version import ModelVersion


def test_disabled_worker_never_opens_dependencies(monkeypatch):
    from app.core.config import Settings
    from app.database import postgres
    from app.workers import tasks

    def forbidden():
        raise AssertionError("disabled inference opened PostgreSQL")

    monkeypatch.setattr(postgres, "get_session_factory", forbidden)
    assert Settings(app_secret="synthetic").organization_forecast_enabled is False
    result = tasks.forecast_organization.run(
        hospital_id="00000000-0000-0000-0000-000000000001",
        model_version="synthetic-v1",
        mapping_version="synthetic-map",
        delivery_watermark="synthetic-delivery",
        origin="2026-09-23",
        horizon_days=7,
    )
    assert result["reason"] == "ORGANIZATION_FORECAST_DISABLED"
    assert result.get("forecast_id") is None


def test_missing_contract_fails_closed_without_loading_model():
    from app.business.forecasting.contracts import OrganizationForecastRequest
    from app.business.forecasting.organization import OrganizationForecastService

    service = OrganizationForecastService(enabled=True)
    result = service.run(
        OrganizationForecastRequest(
            hospital_id=UUID("00000000-0000-0000-0000-000000000001"),
            model_version="synthetic-v1",
            mapping_version="synthetic-map",
            delivery_watermark="synthetic-delivery",
            origin=date(2026, 9, 23),
        )
    )
    assert result["reason"] == "ORGANIZATION_CONTRACT_NOT_CONFIGURED"
    assert result.get("forecast_id") is None


NOW = datetime(2026, 9, 23, 12, tzinfo=UTC)
HOSPITAL = UUID("00000000-0000-0000-0000-000000000001")
REQUEST = OrganizationForecastRequest(
    HOSPITAL, "synthetic-v1", "map-v1", "delivery-v1", NOW.date()
)
HISTORY = tuple(
    DailyReferralCount(NOW.date() - timedelta(days=42 - i), 100) for i in range(42)
)


def registered_model():
    return ModelVersion(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        target="DAILY_REFERRAL_COUNT",
        algorithm="synthetic_model",
        version="synthetic-v1",
        mlflow_run_id="synthetic-run",
        feature_schema_version="hospital-referrals-direct7-v1",
        trained_at=NOW - timedelta(days=60),
        training_period_start=date(2026, 1, 1),
        training_period_end=date(2026, 6, 30),
        training_rows=181,
        forecast_horizon_days=7,
        metrics={"mae": 1.0, "wape": 10.0, "rmse": 2.0},
        baseline_metrics={"mae": 2.0, "wape": 20.0, "rmse": 3.0},
        validation_config={
            "organization_forecast_v1": {
                "model_type": "ML",
                "protocol_sha256": "a" * 64,
                "artifact_sha256": "b" * 64,
                "code_sha256": "c" * 64,
            }
        },
        dataset_watermark={},
        selection_rationale="synthetic only",
        status=ModelVersionStatus.SELECTED,
    )


class MemoryTransactions:
    """Synthetic transaction port; PG lock/atomicity has separate integration tests."""

    def __init__(self):
        self.lock = RLock()
        self.results = {}
        self.forecasts = []
        self.signals = []
        self.points = []
        self.audits = []
        self.model = registered_model()
        self.input = OrganizationForecastInput(
            HOSPITAL, "map-v1", HISTORY, "delivery-v1", NOW, True
        )
        self.revoked = False
        self.crash = False

    @contextmanager
    def transaction(self, operation_id):
        with self.lock:
            self.operation_id = operation_id
            previous = deepcopy(
                (self.results, self.forecasts, self.signals, self.points, self.audits)
            )
            try:
                yield self
                if self.crash:
                    raise RuntimeError("synthetic before commit")
            except BaseException:
                self.results, self.forecasts, self.signals, self.points, self.audits = (
                    previous
                )
                raise

    def terminal_result(self):
        return self.results.get(self.operation_id)

    def registered_model(self, version):
        return self.model if self.model and self.model.version == version else None

    def locked_input(self, _request):
        return self.input

    def recheck(self, _request):
        return not self.revoked

    def finish(self, result, *, forecast=None, points=(), signal=None):
        if forecast:
            self.forecasts.append(forecast)
            self.points.extend(points)
        if signal:
            self.signals.append(signal)
        self.results[self.operation_id] = dict(result)
        self.audits.append(dict(result))
        return dict(result)


class SyntheticEngine:
    def __init__(self):
        self.status = "PASS"
        self.result = ForecastEngineResult(
            organization_evidence={
                "schema_version": "organization-alert-policy-v1",
                "episode_policy": {
                    "version": "referral-growth-v1",
                    "window_days": 7,
                    "reference_days": 28,
                    "min_reference_total": 20,
                    "min_extra_referrals": 10,
                    "growth_threshold_percent": 20,
                },
                "episode_anchor": "2026-07-01",
                "protocol_sha256": "a" * 64,
            },
            generated_at=NOW,
            input_period_start=HISTORY[0].observed_on,
            input_period_end=HISTORY[-1].observed_on,
            training_rows=181,
            feature_schema_version="hospital-referrals-direct7-v1",
            selected_model="synthetic_model",
            selected_model_type="ML",
            model_version="synthetic-v1",
            mlflow_run_id="synthetic-run",
            metrics=ForecastMetricSet(1.0, 10.0, 2.0),
            strongest_baseline="weekly_naive",
            baseline_metrics=ForecastMetricSet(2.0, 20.0, 3.0),
            validation_folds=(),
            candidate_metrics=(),
            selection_rationale="synthetic only",
            points=tuple(
                ForecastPointResult(NOW.date() + timedelta(days=i), 150.0, 100.0)
                for i in range(7)
            ),
        )
        self.after_prediction = lambda: None

    def admission(self, _model, _history):
        return {
            "status": self.status,
            "reason_codes": [],
            "policy_snapshot": {"version": "synthetic"},
        }

    def predict(self, _model, _history):
        self.after_prediction()
        return self.result


def configured(store=None, engine=None):
    from app.business.forecasting.organization import OrganizationForecastService

    store = store or MemoryTransactions()
    engine = engine or SyntheticEngine()
    return (
        OrganizationForecastService(
            enabled=True, repository=store, engine=engine, clock=lambda: NOW
        ),
        store,
        engine,
    )


def test_current_forecast_uses_hospital_scope_and_existing_signal_policy():
    service, store, _ = configured()
    result = service.run(REQUEST)
    assert result["status"] == "COMPLETED"
    assert len(store.forecasts) == len(store.signals) == 1
    assert len(store.points) == 7
    forecast, signal = store.forecasts[0], store.signals[0]
    assert forecast.scope_type == signal.scope_type == DataScopeType.HOSPITAL
    assert forecast.hospital_id == signal.hospital_id == HOSPITAL
    assert forecast.model_version_id == store.model.id
    assert signal.severity == "CRITICAL"
    assert signal.rule_config["warning_percent"] == 20
    assert signal.data_watermark["mapping_version"] == "map-v1"


@pytest.mark.parametrize(
    "status", ["POLICY_NOT_APPROVED", "INSUFFICIENT_DATA", "FAIL", "MAYBE"]
)
def test_non_pass_admission_never_persists_forecast_or_signal(status):
    service, store, engine = configured()
    engine.status = status
    result = service.run(REQUEST)
    assert result["status"] == "SUPPRESSED"
    assert not store.forecasts and not store.signals
    assert len(store.audits) == 1


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ({"coverage_complete": False}, "DELIVERY_INCOMPLETE"),
        ({"mapping_version": "revoked"}, "SCOPE_EVIDENCE_MISMATCH"),
        ({"hospital_id": UUID(int=5)}, "SCOPE_EVIDENCE_MISMATCH"),
        ({"delivery_watermark": "unpublished"}, "SCOPE_EVIDENCE_MISMATCH"),
        (
            {
                "history": tuple(
                    replace(p, observed_on=p.observed_on - timedelta(days=1))
                    for p in HISTORY
                )
            },
            "HISTORY_NOT_CURRENT",
        ),
        ({"history": HISTORY[:10]}, "INSUFFICIENT_HISTORY"),
        ({"as_of": NOW - timedelta(days=8)}, "SOURCE_DATA_STALE"),
    ],
)
def test_unconfirmed_scope_delivery_or_history_suppresses(mutation, reason):
    service, store, _ = configured()
    store.input = replace(store.input, **mutation)
    assert service.run(REQUEST)["reason"] == reason
    assert not store.forecasts and not store.signals


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_invalid_prediction_cannot_create_operational_signal(value):
    service, store, engine = configured()
    engine.result = replace(
        engine.result,
        points=(
            replace(engine.result.points[0], predicted_value=value),
            *engine.result.points[1:],
        ),
    )
    assert service.run(REQUEST)["reason"] == "INVALID_MODEL_OUTPUT"
    assert not store.forecasts and not store.signals


def test_mapping_revocation_at_final_recheck_suppresses():
    service, store, engine = configured()
    engine.after_prediction = lambda: setattr(store, "revoked", True)
    assert service.run(REQUEST)["reason"] == "PUBLICATION_CHANGED"
    assert not store.forecasts and not store.signals


def test_stale_job_is_suppressed():
    service, store, _ = configured()
    assert (
        service.run(replace(REQUEST, origin=NOW.date() - timedelta(days=8)))["reason"]
        == "FORECAST_STALE"
    )
    assert not store.signals


def test_retry_after_commit_before_ack_and_concurrent_retry_have_one_result():
    service, store, _ = configured()
    first = service.run(REQUEST)  # commit succeeded, simulated broker ack lost
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.run(REQUEST), range(8)))
    assert all(result == first for result in results)
    assert len(store.forecasts) == len(store.signals) == len(store.audits) == 1


def test_failure_before_commit_rolls_back_forecast_signal_and_audit_then_recovers():
    service, store, _ = configured()
    store.crash = True
    with pytest.raises(RuntimeError):
        service.run(REQUEST)
    assert (
        not store.forecasts
        and not store.signals
        and not store.audits
        and not store.results
    )
    store.crash = False
    assert service.run(REQUEST)["status"] == "COMPLETED"
    assert len(store.forecasts) == len(store.signals) == len(store.audits) == 1


@pytest.mark.parametrize("value", [None, "150", True, 1e300])
def test_malformed_or_unpersistable_output_is_explicitly_suppressed(value):
    service, store, engine = configured()
    engine.result = replace(
        engine.result,
        points=(
            replace(engine.result.points[0], predicted_value=value),
            *engine.result.points[1:],
        ),
    )
    assert service.run(REQUEST)["reason"] == "INVALID_MODEL_OUTPUT"
    assert not store.forecasts and not store.signals


def test_trusted_metrics_must_also_be_finite():
    service, store, _ = configured()
    store.model.metrics = {"mae": float("nan"), "wape": 10.0, "rmse": 2.0}
    assert service.run(REQUEST)["reason"] == "INVALID_MODEL_OUTPUT"
    assert not store.forecasts


def test_persisted_evidence_never_exposes_review_object_paths():
    service, store, engine = configured()
    engine.admission = lambda _model, _history: {
        "status": "PASS",
        "reason_codes": [],
        "policy_snapshot": {
            "version": "synthetic",
            "min_precision": 0.5,
            "sign_off": {
                "evidence_ref": "private/reviews/owner.json",
                "reviewer_id": "synthetic-person",
                "policy_sha256": "f" * 64,
            },
        },
    }
    assert service.run(REQUEST)["status"] == "COMPLETED"
    payload = __import__("json").dumps(store.forecasts[0].dataset_watermark)
    assert "private/reviews" not in payload and "synthetic-person" not in payload
    assert store.forecasts[0].dataset_watermark["hospital_id"] == str(HOSPITAL)
    assert len(store.forecasts[0].dataset_watermark["input_sha256"]) == 64


@pytest.mark.parametrize(
    "reference,prediction,fires",
    [(50.0, 60.0, True), (49.75, 59.7, False), (19.75, 100.0, False), (20.0, 30.0, True)],
)
def test_admitted_rule_exact_threshold_and_both_floors(reference, prediction, fires):
    from app.business.signals.evaluators import ForecastGrowthEvaluator
    from app.business.signals.policy import SignalPolicy
    from app.shared.signal_engine import ForecastEvidence

    evidence = ForecastEvidence(
        UUID(int=4),
        "synthetic",
        "CURRENT",
        "VALID",
        NOW.date(),
        NOW.date() + timedelta(days=6),
        prediction,
        reference,
        "synthetic",
        "ML",
        "v1",
        NOW,
        {},
    )
    result = ForecastGrowthEvaluator(SignalPolicy()).evaluate(
        evidence, now=NOW, admitted_organization=True
    )
    assert (result.candidate is not None) is fires


def test_same_weekly_episode_identity_survives_new_watermark():
    service, store, _ = configured()
    first = service.run(REQUEST)
    store.input = replace(store.input, delivery_watermark="delivery-v2")
    second = service.run(replace(REQUEST, delivery_watermark="delivery-v2"))
    assert first["forecast_id"] != second["forecast_id"]
    assert first["signal_id"] == second["signal_id"]


def test_organization_signal_records_actual_reference_policy_and_frozen_context():
    service, store, _ = configured()
    service.run(REQUEST)
    signal = store.signals[0]
    assert signal.rule_version == "org-growth-v1"
    assert signal.reference_period_start == NOW.date() - timedelta(days=28)
    assert signal.reference_period_end == NOW.date() - timedelta(days=1)
    assert signal.rule_config["episode_policy"]["reference_days"] == 28
    assert signal.rule_config["episode_policy"]["min_reference_total"] == 20
    assert signal.rule_config["episode_policy"]["min_extra_referrals"] == 10
    assert signal.rule_config["episode_anchor"] == "2026-07-01"
    assert signal.rule_config["cadence_days"] == 7
    assert signal.rule_config["protocol_sha256"] == "a" * 64
    assert signal.evidence["forecast_baseline_value"] == 700.0
    assert signal.evidence["reference_weekly_value"] == 700.0


@pytest.mark.parametrize(
    "context",
    [None, {}, {"schema_version": "organization-alert-policy-v1", "episode_policy": {}}],
)
def test_no_organization_signal_or_forecast_with_unproven_alert_policy(context):
    service, store, runner = configured()
    runner.result = replace(runner.result, organization_evidence=context)
    result = service.run(REQUEST)
    assert result["reason"] == "MODEL_POLICY_MISMATCH"
    assert not store.forecasts and not store.signals
