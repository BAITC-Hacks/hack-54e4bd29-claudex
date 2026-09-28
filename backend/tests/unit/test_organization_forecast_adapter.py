"""Artifact and approval binding tests. All bytes and identities are synthetic."""

import hashlib
import json
import platform
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import numpy
import pytest
import sklearn

from app.business.forecasting.contracts import OrganizationForecastInput
from tests.unit.test_organization_forecast import HISTORY, HOSPITAL, NOW, registered_model


def encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


class VersionedMemoryObjects:
    def __init__(self):
        self.objects = {}

    def put(self, key, payload):
        self.objects[(key, "version-1")] = payload
        return {
            "key": key,
            "version": "version-1",
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    def get(self, key, version):
        return self.objects[(key, version)]


def artifact_fixture():
    data = json.loads(
        (
            Path(__file__).parents[3] / "tests/monitoring/admission-fixture.json"
        ).read_text()
    )
    report, policy = data["report"], data["policy"]
    store = VersionedMemoryObjects()
    model = registered_model()
    root = Path(__file__).parents[3]
    implementation_digest = hashlib.sha256(
        encoded(
            {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in (
                    "ml/monitoring.py",
                    "ml/monitoring_contracts.py",
                    "ml/evaluation/monitoring.py",
                    "ml/evaluation/admission.py",
                )
            }
        )
    ).hexdigest()
    protocol = {
        "schema_version": "monitoring-evaluation-v2",
        "aggregate_manifest_sha256": "a" * 64,
        "implementation_sha256": implementation_digest,
        "dataset_sha256": report["dataset_sha256"],
        "source_manifest_hashes": ["c" * 64],
        "split": {
            "train_end": "2026-05-31",
            "validation_end": "2026-06-30",
            "test_end": "2026-07-28",
            "horizon_days": 7,
        },
        "timezone": "UTC",
        "feature_schema": model.feature_schema_version,
        "mapping_version": report["mapping_version"],
        "code_commit": "d" * 40,
        "estimator": {
            "name": "HistGradientBoostingRegressor",
            "parameters": __import__(
                "sklearn.ensemble", fromlist=["HistGradientBoostingRegressor"]
            )
            .HistGradientBoostingRegressor(
                max_iter=30, random_state=42, early_stopping=False
            )
            .get_params(),
        },
        "random_seed": 42,
        "dependency_versions": {
            "python": platform.python_version(),
            "numpy": numpy.__version__,
            "scikit-learn": sklearn.__version__,
        },
        "eligibility": {"minimum_training_days": 28, "minimum_training_total": 1},
        "episode_policy": {
            "version": "referral-growth-v1",
            "window_days": 7,
            "reference_days": 28,
            "min_reference_total": 20,
            "min_extra_referrals": 10,
            "growth_threshold_percent": 20,
        },
        "baseline_selection": {"selected": "weekly_naive", "selected_on": "validation"},
        "policy_version": policy["version"],
        "uncertainty": {
            "seed": 42,
            "resamples": 200,
            "min_organizations": 2,
            "min_time_blocks": 4,
        },
        "known_development_periods": [{"start": "2025-01-01", "end": "2025-03-31"}],
    }
    artifact = store.put(
        "registered/synthetic-model", b"synthetic model bytes, not pickle"
    )
    frozen = store.put("registered/synthetic-protocol", encoded(protocol))
    report["protocol_sha256"] = frozen["sha256"]
    report["model_artifact_sha256"] = artifact["sha256"]
    report["sealed_period_evidence"]["protocol_sha256"] = frozen["sha256"]
    report["sealed_period_evidence"]["model_artifact_sha256"] = artifact["sha256"]
    reviews = {}
    for name, record in [
        ("policy", policy["sign_off"]),
        ("coverage", report["coverage_evidence"]),
        ("sealed", report["sealed_period_evidence"]),
    ]:
        record["evidence_ref"] = "synthetic-review:" + name
        payload = encoded({k: v for k, v in record.items() if k != "evidence_sha256"})
        ref = store.put("reviews/" + name, payload)
        record["evidence_sha256"] = ref["sha256"]
        reviews[record["evidence_ref"]] = ref
    model.algorithm = "HistGradientBoostingRegressor"
    model.validation_config = {
        "organization_forecast_v1": {
            "schema_version": "organization-model-registry-v1",
            "model_version": model.version,
            "model_type": "ML",
            "feature_schema_version": model.feature_schema_version,
            "artifact": artifact,
            "protocol": frozen,
            "artifact_sha256": artifact["sha256"],
            "protocol_sha256": frozen["sha256"],
            "code_sha256": implementation_digest,
            "code_commit": "d" * 40,
            "hospital_ids": [str(HOSPITAL)],
            "valid_from": "2026-09-01",
            "valid_through": "2026-10-31",
            "report": report,
            "policy": policy,
            "review_objects": reviews,
            "report_object": store.put("registered/report", encoded(report)),
            "policy_object": store.put("registered/policy", encoded(policy)),
        }
    }
    history = OrganizationForecastInput(
        HOSPITAL, report["mapping_version"], HISTORY, "delivery-v1", NOW, True
    )
    return store, model, history


def engine(store, loader=None):
    from app.adapters.organization_forecasting import RegisteredOrganizationEngine

    return RegisteredOrganizationEngine(objects=store, loader=loader)


def test_registered_synthetic_bytes_and_m_admission_can_predict_scoped_aggregate():
    store, model, history = artifact_fixture()
    runner = engine(store, lambda _data: (lambda rows: [150.0] * len(rows)))
    assert runner.admission(model, history)["status"] == "PASS"
    result = runner.predict(model, history)
    assert len(result.points) == 7
    assert result.points[0].forecast_date == NOW.date()
    assert result.points[0].baseline_value == 100.0
    assert result.model_version == model.version


@pytest.mark.parametrize(
    "field,value",
    [
        ("hospital_ids", ["00000000-0000-0000-0000-000000000099"]),
        ("model_version", "different-model"),
        ("model_type", "BASELINE"),
        ("valid_through", "2026-09-22"),
        ("valid_from", "2026-09-24"),
        ("artifact_sha256", "0" * 64),
        ("protocol_sha256", "0" * 64),
        ("feature_schema_version", "unknown"),
        ("code_commit", "0" * 40),
    ],
)
def test_registry_must_bind_actual_input_hospital_model_date_and_provenance(field, value):
    store, model, history = artifact_fixture()
    model.validation_config["organization_forecast_v1"][field] = value
    with pytest.raises(ValueError):
        engine(store).admission(model, history)


def test_mapping_version_cannot_be_substituted_after_evaluation():
    store, model, history = artifact_fixture()
    with pytest.raises(ValueError):
        engine(store).admission(model, replace(history, mapping_version="new-map"))


@pytest.mark.parametrize(
    "key",
    [
        "registered/synthetic-model",
        "registered/synthetic-protocol",
        "reviews/sealed",
        "reviews/coverage",
        "reviews/policy",
        "registered/report",
        "registered/policy",
    ],
)
def test_tampered_registered_objects_never_reach_model_loader(key):
    store, model, history = artifact_fixture()
    store.objects[(key, "version-1")] = b"tampered"

    def forbidden(_data):
        raise AssertionError("tampered artifact reached deserializer")

    runner = engine(store, forbidden)
    with pytest.raises(ValueError):
        runner.predict(model, history)


def test_unsigned_pass_string_and_missing_external_review_are_not_authority():
    store, model, history = artifact_fixture()
    registry = model.validation_config["organization_forecast_v1"]
    registry["admission"] = {"status": "PASS"}
    registry["review_objects"] = {}
    with pytest.raises(ValueError):
        engine(store).admission(model, history)


def test_artifact_without_immutable_object_version_rejected():
    store, model, history = artifact_fixture()
    model.validation_config["organization_forecast_v1"]["artifact"]["version"] = ""
    with pytest.raises(ValueError):
        engine(store).admission(model, history)


def test_protocol_implementation_hash_must_match_registered_code_hash():
    store, model, history = artifact_fixture()
    model.validation_config["organization_forecast_v1"]["code_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        engine(store).admission(model, history)


def test_unapproved_policy_is_explicitly_negative_without_loading_objects():
    store, model, history = artifact_fixture()
    model.validation_config = {
        "organization_forecast_v1": {
            "report": {"independent_test": False, "coverage_complete": False},
            "policy": {"approved": False, "version": "draft-v1"},
        }
    }
    assert engine(store).admission(model, history)["status"] == "POLICY_NOT_APPROVED"


@pytest.mark.parametrize("scenario", ["conflicting_split", "viewed_test"])
def test_hash_consistent_seal_cannot_contradict_protocol_or_reuse_viewed_period(scenario):
    store, model, history = artifact_fixture()
    reg = model.validation_config["organization_forecast_v1"]
    protocol = json.loads(store.get(reg["protocol"]["key"], reg["protocol"]["version"]))
    if scenario == "conflicting_split":
        protocol["split"].update(
            train_end="2026-07-28", validation_end="2026-08-31", test_end="2026-09-28"
        )
    else:
        protocol["known_development_periods"].append(
            {"start": "2026-07-01", "end": "2026-07-28"}
        )
    frozen = store.put(reg["protocol"]["key"], encoded(protocol))
    reg["protocol"] = frozen
    reg["protocol_sha256"] = frozen["sha256"]
    report = reg["report"]
    report["protocol_sha256"] = frozen["sha256"]
    seal = report["sealed_period_evidence"]
    seal["protocol_sha256"] = frozen["sha256"]
    ref = reg["review_objects"][seal["evidence_ref"]]
    ref = store.put(
        ref["key"], encoded({k: v for k, v in seal.items() if k != "evidence_sha256"})
    )
    seal["evidence_sha256"] = ref["sha256"]
    reg["review_objects"][seal["evidence_ref"]] = ref
    reg["report_object"] = store.put(reg["report_object"]["key"], encoded(report))
    with pytest.raises(ValueError):
        engine(store).admission(model, history)


def test_changed_executing_feature_function_is_rejected_before_predictor(monkeypatch):
    from ml.evaluation import monitoring

    store, model, history = artifact_fixture()
    monkeypatch.setattr(monitoring, "features_at", lambda *_args: (999.0,) * 12)

    def forbidden(_data):
        raise AssertionError("changed implementation reached model loader")

    with pytest.raises(ValueError):
        engine(store, forbidden).predict(model, history)


def test_forecast_error_baseline_does_not_substitute_for_admitted_alert_reference():
    from app.business.forecasting.contracts import DailyReferralCount
    from app.business.forecasting.organization import OrganizationForecastService
    from tests.unit.test_organization_forecast import REQUEST, MemoryTransactions

    store, model, history = artifact_fixture()
    history = replace(
        history,
        history=tuple(
            DailyReferralCount(p.observed_on, 100 if i < 35 else 10)
            for i, p in enumerate(history.history)
        ),
    )
    memory = MemoryTransactions()
    memory.model, memory.input = model, history
    service = OrganizationForecastService(
        enabled=True,
        repository=memory,
        engine=engine(store, lambda _data: lambda rows: [15.0] * len(rows)),
        clock=lambda: NOW,
    )
    result = service.run(replace(REQUEST, mapping_version=history.mapping_version))
    assert result["status"] == "COMPLETED"
    assert not memory.signals
    assert sum(p.baseline_value for p in memory.points) == 70.0


def test_only_aligned_weekly_origins_can_emit_operational_alerts():
    from app.business.forecasting.organization import OrganizationForecastService
    from tests.unit.test_organization_forecast import REQUEST, MemoryTransactions

    store, model, history = artifact_fixture()
    emitted = []
    for offset in range(7):
        today = NOW + timedelta(days=offset)
        shifted = replace(
            history,
            as_of=today,
            history=tuple(
                replace(p, observed_on=p.observed_on + timedelta(days=offset))
                for p in history.history
            ),
        )
        memory = MemoryTransactions()
        memory.model, memory.input = model, shifted
        service = OrganizationForecastService(
            enabled=True,
            repository=memory,
            engine=engine(store, lambda _data: lambda rows: [150.0] * len(rows)),
            clock=lambda today=today: today,
        )
        result = service.run(
            replace(REQUEST, origin=today.date(), mapping_version=shifted.mapping_version)
        )
        assert result["status"] == "COMPLETED"
        emitted.extend(memory.signals)
    assert len(emitted) == 1
    assert emitted[0].evaluation_period_start == NOW.date()


def rebind_protocol(store, model, protocol):
    reg = model.validation_config["organization_forecast_v1"]
    reg["protocol"] = store.put(reg["protocol"]["key"], encoded(protocol))
    reg["protocol_sha256"] = reg["protocol"]["sha256"]
    reg["report"]["protocol_sha256"] = reg["protocol_sha256"]
    seal = reg["report"]["sealed_period_evidence"]
    seal["protocol_sha256"] = reg["protocol_sha256"]
    ref = reg["review_objects"][seal["evidence_ref"]]
    ref = store.put(
        ref["key"], encoded({k: v for k, v in seal.items() if k != "evidence_sha256"})
    )
    seal["evidence_sha256"] = ref["sha256"]
    reg["review_objects"][seal["evidence_ref"]] = ref
    reg["report_object"] = store.put(reg["report_object"]["key"], encoded(reg["report"]))


@pytest.mark.parametrize("changed", ["implementation", "dependency"])
def test_hash_consistent_registration_must_match_actual_deployment(changed):
    store, model, history = artifact_fixture()
    reg = model.validation_config["organization_forecast_v1"]
    protocol = json.loads(store.get(reg["protocol"]["key"], reg["protocol"]["version"]))
    if changed == "implementation":
        protocol["implementation_sha256"] = "f" * 64
        reg["code_sha256"] = "f" * 64
    else:
        protocol["dependency_versions"]["python"] = "3.12.0"
    rebind_protocol(store, model, protocol)

    def forbidden(_data):
        raise AssertionError("deployment mismatch reached deserializer")

    runner = engine(store, forbidden)
    with pytest.raises(ValueError, match="RUNTIME_"):
        runner.admission(model, history)
    with pytest.raises(ValueError, match="RUNTIME_"):
        runner.predict(model, history)


def test_loaded_code_mutation_is_rejected_by_admission_itself(monkeypatch):
    from ml.evaluation import monitoring

    store, model, history = artifact_fixture()
    monkeypatch.setattr(monitoring, "features_at", lambda *_args: (999.0,) * 12)
    with pytest.raises(ValueError, match="RUNTIME_IMPLEMENTATION_MISMATCH"):
        engine(store).admission(model, history)
