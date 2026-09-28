"""Synthetic boundary tests: temporal leakage, coverage and immutable provenance."""

import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta

import pytest

from ml import monitoring


def api():
    from ml import monitoring_contracts as contracts
    from ml.evaluation import monitoring as evaluation

    return contracts, evaluation


def fixture(days=90, unknown=False):
    c, e = api()
    start = date(2026, 1, 1)
    rows = [
        {
            "organization_id": "approved-A",
            "day": (start + timedelta(days=i)).isoformat(),
            "value": i % 7 + 1,
        }
        for i in range(days)
    ]
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest = c.AggregateManifest(
        "approved-aggregate-v1",
        start,
        start + timedelta(days=days - 1),
        start + timedelta(days=days - 2 if unknown else days - 1),
        ("approved-A",),
        "mapping-v1",
        start,
        "mapping-review:fixture",
        "delivery-review:fixture",
        digest,
    )
    return c, e, rows, manifest


def protocol_payload():
    return {
        "schema_version": "monitoring-evaluation-v2",
        "aggregate_manifest_sha256": "a" * 64,
        "dataset_sha256": "b" * 64,
        "source_manifest_hashes": ["c" * 64],
        "split": {
            "train_end": "2026-02-28",
            "validation_end": "2026-03-14",
            "test_end": "2026-03-28",
            "horizon_days": 7,
        },
        "timezone": "Asia/Qyzylorda",
        "feature_schema": "hospital-referrals-direct7-v1",
        "mapping_version": "mapping-v1",
        "implementation_sha256": "d" * 64,
        "code_commit": "d965aff1665eeeff7e62d26be59beeef88324228",
        "estimator": {
            "name": "HistGradientBoostingRegressor",
            "parameters": {
                "categorical_features": None,
                "early_stopping": False,
                "interaction_cst": None,
                "l2_regularization": 0.0,
                "learning_rate": 0.1,
                "loss": "squared_error",
                "max_bins": 255,
                "max_depth": None,
                "max_features": 1.0,
                "max_iter": 30,
                "max_leaf_nodes": 31,
                "min_samples_leaf": 20,
                "monotonic_cst": None,
                "n_iter_no_change": 10,
                "quantile": None,
                "random_state": 42,
                "scoring": "loss",
                "tol": 1e-7,
                "validation_fraction": 0.1,
                "verbose": 0,
                "warm_start": False,
            },
        },
        "random_seed": 42,
        "dependency_versions": {
            "python": "3.12.12",
            "numpy": "2.2.6",
            "scikit-learn": "1.7.2",
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
        "policy_version": "draft-v1",
        "uncertainty": {
            "seed": 42,
            "resamples": 200,
            "min_organizations": 2,
            "min_time_blocks": 4,
        },
        "known_development_periods": [{"start": "2025-01-01", "end": "2025-03-31"}],
    }


def test_contract_is_available_without_backend_imports():
    import importlib.util

    assert importlib.util.find_spec("ml.monitoring_contracts") is not None


def test_training_origin_cannot_use_validation_outcome():
    c, _ = api()
    split = c.SplitSpec(date(2025, 3, 3), date(2025, 3, 17), date(2025, 3, 31))
    assert c.label_within_training(date(2025, 2, 24), split)
    assert not c.label_within_training(date(2025, 2, 25), split)
    with pytest.raises(ValueError):
        c.SplitSpec(split.validation_end, split.train_end, split.test_end)


def test_complete_absence_is_zero_but_incomplete_delivery_is_unknown():
    c, e, rows, manifest = fixture()
    from dataclasses import replace

    rows = rows[:-1]
    manifest = replace(manifest, aggregate_sha256=c.canonical_sha256(rows))
    complete = e.load_approved_aggregates(rows, manifest)[0]
    assert complete.observations[-1].value == 0
    assert complete.observations[-1].delivery_complete
    partial = e.load_approved_aggregates(
        rows, replace(manifest, confirmed_complete_through=date(2026, 3, 30))
    )[0]
    assert partial.observations[-1].value is None
    result = e.forecast_at([partial], date(2026, 3, 31), predictor=lambda x: [1] * len(x))
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["forecasts"] == {}


def test_manifest_integrity_and_approved_population_are_enforced():
    c, e, rows, manifest = fixture()
    with pytest.raises(ValueError, match="hash"):
        e.load_approved_aggregates(rows[:-1], manifest)
    from dataclasses import replace

    rows[0]["organization_id"] = "unapproved"
    with pytest.raises(ValueError, match="population"):
        e.load_approved_aggregates(
            rows, replace(manifest, aggregate_sha256=c.canonical_sha256(rows))
        )
    with pytest.raises(ValueError):
        replace(manifest, delivery_evidence_ref="")


def test_future_mutation_cannot_change_features_eligibility_or_predictions():
    c, e, rows, manifest = fixture()
    from dataclasses import replace

    series = e.load_approved_aggregates(rows, manifest)
    altered = deepcopy(rows)
    for row in altered[59:]:
        row["value"] = 100000
    changed = e.load_approved_aggregates(
        altered, replace(manifest, aggregate_sha256=c.canonical_sha256(altered))
    )
    split = c.SplitSpec(date(2026, 2, 28), date(2026, 3, 14), date(2026, 3, 31))
    assert e.eligible_organizations(series, split, minimum_total=9999) == ()
    assert e.eligible_organizations(changed, split, minimum_total=9999) == ()
    for h in range(1, 8):
        assert e.features_at(series[0], split.train_end, h) == e.features_at(
            changed[0], split.train_end, h
        )

    def prediction(x):
        return [row[0] for row in x]

    assert e.forecast_at(series, split.train_end, prediction) == e.forecast_at(
        changed, split.train_end, prediction
    )
    assert e.training_samples(series, split) == e.training_samples(changed, split)
    samples = e.training_samples(series, split)
    assert samples and max(s.origin for s in samples) == date(2026, 2, 21)
    unavailable = replace(series[0], mapping_available_on=date(2026, 3, 1))
    assert e.eligible_organizations([unavailable], split) == ()
    assert (
        e.forecast_at([unavailable], split.train_end, prediction)["status"]
        == "INSUFFICIENT_DATA"
    )


def test_protocol_is_immutable_canonical_and_provenance_sensitive():
    c, _ = api()
    payload = protocol_payload()
    protocol = c.freeze_protocol(payload)
    same = c.freeze_protocol(dict(reversed(list(payload.items()))))
    assert protocol.sha256 == same.sha256
    payload["estimator"]["parameters"]["random_state"] = 7
    assert protocol.snapshot()["estimator"]["parameters"]["random_state"] == 42
    out = protocol.snapshot()
    out["dependency_versions"]["numpy"] = "changed"
    assert protocol.sha256 == same.sha256
    with pytest.raises((AttributeError, TypeError)):
        protocol.canonical_json = "{}"
    payload = protocol_payload()
    payload["mapping_version"] = "mapping-v2"
    assert c.freeze_protocol(payload).sha256 != protocol.sha256
    for key in protocol_payload():
        broken = protocol_payload()
        del broken[key]
        with pytest.raises(ValueError):
            c.freeze_protocol(broken)


def test_new_entrypoint_only_consumes_approved_aggregates():
    c, _, rows, manifest = fixture()
    result = monitoring.prepare_approved_experiment(
        rows,
        manifest,
        c.SplitSpec(date(2026, 2, 28), date(2026, 3, 14), date(2026, 3, 31)),
    )
    assert result["eligible_organizations"] == ("approved-A",)
    assert result["path_version"] == "approved-aggregate-v2"


def test_validation_windows_do_not_cross_test_and_predictions_are_frozen():
    c, e, rows, manifest = fixture()
    series = e.load_approved_aggregates(rows, manifest)
    split = c.SplitSpec(date(2026, 2, 28), date(2026, 3, 14), date(2026, 3, 31))
    result = e.walk_forward_score(
        series, split, lambda x: [1.0] * len(x), partition="validation"
    )
    assert len(result["windows"]) == 2
    assert result["windows"][-1]["end"] == "2026-03-14"
    assert result["ml"]["points"] == 14
    assert result["weekly_naive"]["mae"] == 0
    assert result["mean7"]["mae"] == pytest.approx(12 / 7)


def test_frozen_protocol_drives_end_to_end_aggregate_evaluation():
    c, e, rows, manifest = fixture()
    payload = protocol_payload()
    payload["aggregate_manifest_sha256"] = manifest.sha256
    payload["dataset_sha256"] = manifest.aggregate_sha256
    protocol = c.freeze_protocol(payload)
    assert hasattr(e, "evaluate_protocol"), "frozen protocol is not yet consumed"
    result = e.evaluate_protocol(
        rows, manifest, protocol, lambda x: [row[0] for row in x], partition="validation"
    )
    assert result["protocol_sha256"] == protocol.sha256
    assert result["baseline"] == "weekly_naive"
    assert result["episode_metrics"]["sample_support"]["org_weeks"] == 2
    assert result["uncertainty"]["reason"] == "TOO_FEW_INDEPENDENT_CLUSTERS"
    payload["dataset_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="provenance"):
        e.evaluate_protocol(
            rows, manifest, c.freeze_protocol(payload), lambda x: [1] * len(x)
        )


def test_unknown_test_outcomes_do_not_call_predictor_or_count_negatives():
    c, e, rows, manifest = fixture(unknown=True)
    series = e.load_approved_aggregates(rows, manifest)
    split = c.SplitSpec(date(2026, 2, 28), date(2026, 3, 17), date(2026, 3, 31))
    calls = []
    result = e.walk_forward_score(
        series, split, lambda x: calls.append(x) or [1] * len(x), partition="test"
    )
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["ml"]["points"] == 7
    assert len(result["excluded_windows"]) == 1
    assert len(calls) == 1


@pytest.mark.parametrize("value", [[], {"approved": True}, None])
def test_protocol_nested_malformed_provenance_is_value_error(value):
    c, _ = api()
    payload = protocol_payload()
    payload["dependency_versions"] = value
    with pytest.raises(ValueError):
        c.freeze_protocol(payload)


def test_freezing_rejects_missing_estimator_parameters_not_silent_defaults():
    c, _ = api()
    payload = protocol_payload()
    payload["estimator"]["parameters"] = {"random_state": 42}
    with pytest.raises(ValueError, match="parameters"):
        c.freeze_protocol(payload)


def test_protocol_fingerprint_binds_uncommitted_implementation():
    c, _ = api()
    payload = protocol_payload()
    payload["implementation_sha256"] = "d" * 64
    first = c.freeze_protocol(payload)
    payload["implementation_sha256"] = "e" * 64
    assert c.freeze_protocol(payload).sha256 != first.sha256


def test_protocol_zero_activity_eligibility_is_not_overridden_by_evaluator():
    c, e, rows, manifest = fixture()
    from dataclasses import replace

    for row in rows:
        row["value"] = 0
    manifest = replace(manifest, aggregate_sha256=c.canonical_sha256(rows))
    payload = protocol_payload()
    payload["aggregate_manifest_sha256"] = manifest.sha256
    payload["dataset_sha256"] = manifest.aggregate_sha256
    payload["eligibility"]["minimum_training_total"] = 0
    result = e.evaluate_protocol(
        rows, manifest, c.freeze_protocol(payload), lambda x: [0] * len(x)
    )
    assert result["ml"]["points"] == 14
    assert result["episode_metrics"]["counts"]["tn"] == 2
