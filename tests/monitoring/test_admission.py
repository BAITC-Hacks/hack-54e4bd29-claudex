"""Only synthetic review records; no fixture is real approval."""

import json
from copy import deepcopy
from pathlib import Path

import pytest


def fixture():
    data = json.loads(Path(__file__).with_name("admission-fixture.json").read_text())
    return data["report"], data["policy"]


def evaluate(report, policy):
    from ml.evaluation.admission import evaluate_admission

    return evaluate_admission(report, policy)


def resign(policy):
    from ml.monitoring_contracts import canonical_sha256

    policy["sign_off"]["policy_sha256"] = canonical_sha256(
        {k: v for k, v in policy.items() if k != "sign_off"}
    )


def test_admission_interface_exists():
    import importlib.util

    assert importlib.util.find_spec("ml.evaluation.admission") is not None


def test_no_approved_policy_cannot_promote_a_model():
    result = evaluate(
        {"independent_test": False, "coverage_complete": False},
        {"approved": False, "version": "draft-v1"},
    )
    assert result["status"] == "POLICY_NOT_APPROVED"
    assert result["reason_codes"] == ["OWNER_ACCEPTANCE_REQUIRED"]


def test_complete_synthetic_evidence_passes_all_gates_without_mutating_inputs():
    report, policy = fixture()
    before = deepcopy((report, policy))
    result = evaluate(report, policy)
    assert result == {"status": "PASS", "reason_codes": [], "policy_snapshot": policy}
    assert (report, policy) == before
    result["policy_snapshot"]["sign_off"]["reviewer_id"] = "changed"
    assert policy["sign_off"]["reviewer_id"] == "synthetic-reviewer"


@pytest.mark.parametrize(
    "field",
    [
        "min_precision",
        "min_recall",
        "max_false_alerts_per_org_week",
        "min_positive_episodes",
        "min_organizations",
        "min_evaluation_windows",
        "max_forecast_error_vs_baseline",
        "sign_off",
    ],
)
def test_approved_policy_cannot_omit_any_release_gate(field):
    report, policy = fixture()
    del policy[field]
    with pytest.raises(ValueError):
        evaluate(report, policy)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_precision", 1.1),
        ("min_recall", -0.1),
        ("min_recall", True),
        ("min_recall", "0.5"),
        ("min_organizations", 1.5),
        ("min_positive_episodes", 0),
        ("max_false_alerts_per_org_week", -1),
        ("max_forecast_error_vs_baseline", float("nan")),
        ("min_precision", float("inf")),
    ],
)
def test_malformed_policy_bounds_raise(field, value):
    report, policy = fixture()
    policy[field] = value
    with pytest.raises(ValueError):
        evaluate(report, policy)


@pytest.mark.parametrize("field", ["independent_test", "coverage_complete"])
def test_boolean_claim_is_not_evidence(field):
    report, policy = fixture()
    report[field] = False
    assert evaluate(report, policy)["status"] == "INSUFFICIENT_DATA"


@pytest.mark.parametrize("field", ["coverage_evidence", "sealed_period_evidence"])
def test_missing_review_cannot_pass_on_boolean_flags(field):
    report, policy = fixture()
    report[field] = None
    assert evaluate(report, policy)["status"] == "INSUFFICIENT_DATA"


@pytest.mark.parametrize("field", ["coverage_evidence", "sealed_period_evidence"])
def test_unverified_external_record_is_insufficient(field):
    report, policy = fixture()
    report[field]["review_status"] = "UNVERIFIED"
    assert evaluate(report, policy)["status"] == "INSUFFICIENT_DATA"


def test_policy_approval_requires_review_bound_to_exact_policy():
    report, policy = fixture()
    policy["sign_off"] = None
    assert evaluate(report, policy)["status"] == "POLICY_NOT_APPROVED"
    report, policy = fixture()
    policy["min_precision"] = 0.1
    assert evaluate(report, policy)["status"] == "POLICY_NOT_APPROVED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unseen_before_open", False),
        ("no_test_tuning", False),
        ("protocol_sha256", "f" * 64),
        ("model_artifact_sha256", "f" * 64),
        ("dataset_sha256", "f" * 64),
        ("policy_sha256", "f" * 64),
        ("frozen_at", "2026-08-02T00:00:00+00:00"),
        ("sealed_at", "2026-08-02T00:00:00+00:00"),
    ],
)
def test_false_independence_or_mismatched_seal_never_passes(field, value):
    report, policy = fixture()
    report["sealed_period_evidence"][field] = value
    assert evaluate(report, policy)["status"] == "INSUFFICIENT_DATA"


def test_q1_replay_is_never_new_independent_evidence():
    report, policy = fixture()
    report["sealed_period_evidence"].update(
        train_end="2025-01-01",
        validation_end="2025-02-28",
        test_start="2025-03-01",
        test_end="2025-03-28",
    )
    assert evaluate(report, policy)["status"] == "INSUFFICIENT_DATA"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_positive_episodes", 6),
        ("min_organizations", 3),
        ("min_evaluation_windows", 5),
    ],
)
def test_insufficient_support_precedes_metric_comparison(field, value):
    report, policy = fixture()
    policy[field] = value
    resign(policy)
    report["sealed_period_evidence"]["policy_sha256"] = policy["sign_off"][
        "policy_sha256"
    ]
    result = evaluate(report, policy)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert "INSUFFICIENT_SAMPLE_SUPPORT" in result["reason_codes"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("min_precision", 0.9, "PRECISION_BELOW_MINIMUM"),
        ("min_recall", 0.9, "RECALL_BELOW_MINIMUM"),
        ("max_false_alerts_per_org_week", 0.1, "FALSE_ALERT_BUDGET_EXCEEDED"),
        ("max_forecast_error_vs_baseline", 0.4, "FORECAST_BASELINE_GATE_FAILED"),
    ],
)
def test_each_single_failed_threshold_blocks_promotion(field, value, reason):
    report, policy = fixture()
    policy[field] = value
    resign(policy)
    report["sealed_period_evidence"]["policy_sha256"] = policy["sign_off"][
        "policy_sha256"
    ]
    result = evaluate(report, policy)
    assert result["status"] == "FAIL"
    assert result["reason_codes"] == [reason]


def test_undefined_wape_and_zero_baseline_error_cannot_be_favorable():
    report, policy = fixture()
    report["forecast_metrics"]["wape"] = None
    assert evaluate(report, policy)["status"] == "INSUFFICIENT_DATA"
    report, policy = fixture()
    report["baseline_metrics"]["mae"] = 0
    assert evaluate(report, policy)["status"] == "FAIL"


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "missing",
        "count_bool",
        "count_negative",
        "metric_nan",
        "count_support",
        "workload",
        "bad_hash",
        "review_missing",
        "naive_timestamp",
        "invalid_split",
    ],
)
def test_malformed_report_is_rejected_at_boundary(mutation):
    report, policy = fixture()
    if mutation == "unknown":
        report["approval"] = True
    if mutation == "missing":
        del report["counts"]
    if mutation == "count_bool":
        report["counts"]["tp"] = True
    if mutation == "count_negative":
        report["counts"]["fp"] = -1
    if mutation == "metric_nan":
        report["forecast_metrics"]["mae"] = float("nan")
    if mutation == "count_support":
        report["sample_support"]["org_weeks"] = 9
    if mutation == "workload":
        report["false_alerts_per_org_week"] = 0
    if mutation == "bad_hash":
        report["protocol_sha256"] = "not-a-hash"
    if mutation == "review_missing":
        del report["sealed_period_evidence"]["evidence_ref"]
    if mutation == "naive_timestamp":
        report["sealed_period_evidence"]["opened_at"] = "2026-08-01T00:00:00"
    if mutation == "invalid_split":
        report["sealed_period_evidence"]["train_end"] = "2026-07-30"
    with pytest.raises(ValueError):
        evaluate(report, policy)


def test_empty_report_cannot_claim_positive_cluster_support():
    report, policy = fixture()
    report["counts"] = dict.fromkeys(("tp", "fp", "fn", "tn"), 0)
    report["sample_support"]["org_weeks"] = 0
    report["sample_support"]["positive_episodes"] = 0
    report["alerts_per_org_week"] = report["false_alerts_per_org_week"] = None
    report["forecast_metrics"] = report["baseline_metrics"] = {
        "mae": None,
        "wape": None,
        "points": 0,
    }
    with pytest.raises(ValueError):
        evaluate(report, policy)


def test_overflow_numeric_payload_has_predictable_value_error():
    report, policy = fixture()
    policy["max_forecast_error_vs_baseline"] = 10**1000
    with pytest.raises(ValueError):
        evaluate(report, policy)
