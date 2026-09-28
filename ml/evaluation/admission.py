"""Pure, fail-closed release gate over trusted server-resolved review evidence.

This boundary validates content; it cannot authenticate a review record. The
caller must resolve and authenticate records from server persistence first.
"""

from __future__ import annotations

import math
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import TypedDict, cast

from ml.monitoring_contracts import canonical_sha256, require_sha256, require_text


class _Review(TypedDict):
    review_status: str
    reviewer_id: str
    evidence_ref: str
    evidence_sha256: str


class _SignOff(_Review):
    policy_sha256: str


class _ApprovedPolicy(TypedDict):
    approved: bool
    version: str
    min_precision: float
    min_recall: float
    max_false_alerts_per_org_week: float
    min_positive_episodes: int
    min_organizations: int
    min_evaluation_windows: int
    max_forecast_error_vs_baseline: float
    sign_off: _SignOff | None


class _Coverage(_Review):
    dataset_sha256: str
    mapping_version: str
    expected_org_days: int
    complete_org_days: int
    period_start: str
    period_end: str


class _SealedPeriod(_Review):
    dataset_sha256: str
    protocol_sha256: str
    model_artifact_sha256: str
    policy_sha256: str
    train_end: str
    validation_end: str
    test_start: str
    test_end: str
    frozen_at: str
    sealed_at: str
    opened_at: str
    unseen_before_open: bool
    no_test_tuning: bool


class _ForecastMetrics(TypedDict):
    mae: float | None
    wape: float | None
    points: int


class _Report(TypedDict):
    schema_version: str
    independent_test: bool
    coverage_complete: bool
    protocol_sha256: str
    model_artifact_sha256: str
    dataset_sha256: str
    mapping_version: str
    counts: dict[str, int]
    forecast_metrics: _ForecastMetrics
    baseline_metrics: _ForecastMetrics
    alerts_per_org_week: float | None
    false_alerts_per_org_week: float | None
    sample_support: dict[str, int]
    coverage_evidence: _Coverage | None
    sealed_period_evidence: _SealedPeriod | None


POLICY_FIELDS = {
    "approved",
    "version",
    "min_precision",
    "min_recall",
    "max_false_alerts_per_org_week",
    "min_positive_episodes",
    "min_organizations",
    "min_evaluation_windows",
    "max_forecast_error_vs_baseline",
    "sign_off",
}
REPORT_FIELDS = {
    "schema_version",
    "independent_test",
    "coverage_complete",
    "protocol_sha256",
    "model_artifact_sha256",
    "dataset_sha256",
    "mapping_version",
    "counts",
    "forecast_metrics",
    "baseline_metrics",
    "alerts_per_org_week",
    "false_alerts_per_org_week",
    "sample_support",
    "coverage_evidence",
    "sealed_period_evidence",
}
REVIEW_FIELDS = {"review_status", "reviewer_id", "evidence_ref", "evidence_sha256"}
COVERAGE_FIELDS = REVIEW_FIELDS | {
    "dataset_sha256",
    "mapping_version",
    "expected_org_days",
    "complete_org_days",
    "period_start",
    "period_end",
}
SEALED_FIELDS = REVIEW_FIELDS | {
    "dataset_sha256",
    "protocol_sha256",
    "model_artifact_sha256",
    "policy_sha256",
    "train_end",
    "validation_end",
    "test_start",
    "test_end",
    "frozen_at",
    "sealed_at",
    "opened_at",
    "unseen_before_open",
    "no_test_tuning",
}


def _shape(value: object, keys: set[str], name: str) -> None:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{name}: missing or unknown fields")


def _bool(value: object) -> None:
    if type(value) is not bool:
        raise ValueError("Expected boolean")


def _number(
    value: object,
    *,
    integer: bool = False,
    minimum: float = 0,
    maximum: float | None = None,
    nullable: bool = False,
) -> None:
    if value is None and nullable:
        return
    if type(value) is int and abs(value) > 2**53:
        raise ValueError("Numeric value exceeds exact JSON integer range")
    if type(value) is not int and type(value) is not float:
        raise ValueError("Invalid finite numeric bound")
    if (
        (integer and type(value) is not int)
        or not math.isfinite(value)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        raise ValueError("Invalid finite numeric bound")


def _day(value: object) -> date:
    if type(value) is not str:
        raise ValueError("Expected ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Expected ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError("Expected canonical ISO date")
    return parsed


def _timestamp(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("Expected timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Expected timezone-aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Expected timezone-aware ISO timestamp")
    return parsed


def _review(evidence: dict) -> None:
    if evidence["review_status"] not in ("VERIFIED_EXTERNAL", "UNVERIFIED"):
        raise ValueError("Unknown external review status")
    for key in ("reviewer_id", "evidence_ref"):
        require_text(evidence[key])
    require_sha256(evidence["evidence_sha256"])


def _validate_policy(policy: dict) -> None:
    if (
        type(policy) is not dict
        or not {"approved", "version"} <= set(policy)
        or not set(policy) <= POLICY_FIELDS
    ):
        raise ValueError("Malformed policy")
    _bool(policy["approved"])
    require_text(policy["version"])
    if policy["approved"]:
        _shape(policy, POLICY_FIELDS, "approved policy")
    for key in ("min_precision", "min_recall"):
        if key in policy:
            _number(policy[key], maximum=1)
    for key in ("max_false_alerts_per_org_week", "max_forecast_error_vs_baseline"):
        if key in policy:
            _number(policy[key])
    for key in ("min_positive_episodes", "min_organizations", "min_evaluation_windows"):
        if key in policy:
            _number(policy[key], integer=True, minimum=1)
    if policy.get("sign_off") is not None:
        _shape(policy["sign_off"], REVIEW_FIELDS | {"policy_sha256"}, "sign_off")
        _review(policy["sign_off"])
        require_sha256(policy["sign_off"]["policy_sha256"])


def _validate_report(report: dict, *, allow_minimal: bool) -> None:
    if (
        allow_minimal
        and type(report) is dict
        and set(report) == {"independent_test", "coverage_complete"}
    ):
        _bool(report["independent_test"])
        _bool(report["coverage_complete"])
        return
    _shape(report, REPORT_FIELDS, "report")
    if report["schema_version"] != "approved-monitoring-report-v1":
        raise ValueError("Unsupported report schema")
    for key in ("independent_test", "coverage_complete"):
        _bool(report[key])
    for key in ("protocol_sha256", "model_artifact_sha256", "dataset_sha256"):
        require_sha256(report[key])
    require_text(report["mapping_version"])
    counts, support = report["counts"], report["sample_support"]
    _shape(counts, {"tp", "fp", "fn", "tn"}, "counts")
    _shape(
        support,
        {"organizations", "evaluation_windows", "org_weeks", "positive_episodes"},
        "support",
    )
    for value in (*counts.values(), *support.values()):
        _number(value, integer=True)
    weeks = support["org_weeks"]
    if (
        sum(counts.values()) != weeks
        or support["positive_episodes"] != counts["tp"] + counts["fn"]
        or weeks > support["organizations"] * support["evaluation_windows"]
    ):
        raise ValueError("Inconsistent counts and sample support")
    if support["organizations"] > weeks or support["evaluation_windows"] > weeks:
        raise ValueError("Impossible cluster support")
    for key, numerator in (
        ("alerts_per_org_week", counts["tp"] + counts["fp"]),
        ("false_alerts_per_org_week", counts["fp"]),
    ):
        value = report[key]
        _number(value, nullable=True)
        expected = numerator / weeks if weeks else None
        if (value is None) != (expected is None) or (
            value is not None
            and expected is not None
            and not math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-12)
        ):
            raise ValueError("Workload denominator mismatch")
    for name in ("forecast_metrics", "baseline_metrics"):
        metric = report[name]
        _shape(metric, {"mae", "wape", "points"}, name)
        _number(metric["mae"], nullable=True)
        _number(metric["wape"], nullable=True)
        _number(metric["points"], integer=True)
        if metric["points"] != weeks * 7 or (
            metric["points"] == 0
            and (metric["mae"] is not None or metric["wape"] is not None)
        ):
            raise ValueError("Forecast metric support mismatch")
    evidence = report["coverage_evidence"]
    if evidence is not None:
        _shape(evidence, COVERAGE_FIELDS, "coverage_evidence")
        _review(evidence)
        require_sha256(evidence["dataset_sha256"])
        require_text(evidence["mapping_version"])
        for key in ("expected_org_days", "complete_org_days"):
            _number(evidence[key], integer=True)
        if evidence["complete_org_days"] > evidence["expected_org_days"] or _day(
            evidence["period_start"]
        ) > _day(evidence["period_end"]):
            raise ValueError("Invalid coverage evidence")
    evidence = report["sealed_period_evidence"]
    if evidence is not None:
        _shape(evidence, SEALED_FIELDS, "sealed_period_evidence")
        _review(evidence)
        for key in (
            "dataset_sha256",
            "protocol_sha256",
            "model_artifact_sha256",
            "policy_sha256",
        ):
            require_sha256(evidence[key])
        for key in ("unseen_before_open", "no_test_tuning"):
            _bool(evidence[key])
        train, validation, start, end = (
            _day(evidence[key])
            for key in ("train_end", "validation_end", "test_start", "test_end")
        )
        if (
            not train < validation < start <= end
            or start != validation + timedelta(days=1)
            or (end - start).days % 7 != 6
        ):
            raise ValueError("Invalid sealed temporal split")
        for key in ("frozen_at", "sealed_at", "opened_at"):
            _timestamp(evidence[key])


def evaluate_admission(
    report: dict[str, object], policy: dict[str, object]
) -> dict[str, object]:
    """Policy first, external evidence and support next, conjunctive quality last."""
    _validate_policy(policy)
    _validate_report(report, allow_minimal=not policy["approved"])
    snapshot = deepcopy(policy)

    def result(status: str, reasons: list[str]) -> dict[str, object]:
        return {"status": status, "reason_codes": reasons, "policy_snapshot": snapshot}

    ph = canonical_sha256(
        {key: value for key, value in policy.items() if key != "sign_off"}
    )
    if not policy["approved"]:
        return result("POLICY_NOT_APPROVED", ["OWNER_ACCEPTANCE_REQUIRED"])
    # Both validators above checked every field before this typed internal view.
    # A draft policy/minimal report returns before either full-schema cast.
    approved_policy = cast(_ApprovedPolicy, policy)
    validated_report = cast(_Report, report)
    sign_off = approved_policy["sign_off"]
    if (
        sign_off is None
        or sign_off["review_status"] != "VERIFIED_EXTERNAL"
        or sign_off["policy_sha256"] != ph
    ):
        return result("POLICY_NOT_APPROVED", ["OWNER_ACCEPTANCE_REQUIRED"])
    reasons = []
    sealed = validated_report["sealed_period_evidence"]
    if (
        not validated_report["independent_test"]
        or sealed is None
        or sealed["review_status"] != "VERIFIED_EXTERNAL"
    ):
        reasons.append("INDEPENDENT_SEALED_PERIOD_REQUIRED")
    elif (
        not sealed["unseen_before_open"]
        or not sealed["no_test_tuning"]
        or sealed["protocol_sha256"] != validated_report["protocol_sha256"]
        or sealed["model_artifact_sha256"] != validated_report["model_artifact_sha256"]
        or sealed["dataset_sha256"] != validated_report["dataset_sha256"]
        or sealed["policy_sha256"] != ph
        or not _timestamp(sealed["frozen_at"]) < _timestamp(sealed["opened_at"])
        or not _timestamp(sealed["sealed_at"]) < _timestamp(sealed["opened_at"])
        or _timestamp(sealed["opened_at"]).date() <= _day(sealed["test_end"])
        or _day(sealed["test_start"]) <= date(2025, 3, 31)
    ):
        reasons.append("SEALED_PERIOD_EVIDENCE_INVALID")
    coverage = validated_report["coverage_evidence"]
    support = validated_report["sample_support"]
    if (
        not validated_report["coverage_complete"]
        or coverage is None
        or coverage["review_status"] != "VERIFIED_EXTERNAL"
    ):
        reasons.append("COMPLETE_COVERAGE_EVIDENCE_REQUIRED")
    elif (
        coverage["dataset_sha256"] != validated_report["dataset_sha256"]
        or coverage["mapping_version"] != validated_report["mapping_version"]
        or coverage["expected_org_days"] == 0
        or coverage["complete_org_days"] != coverage["expected_org_days"]
        or support["org_weeks"]
        != support["organizations"] * support["evaluation_windows"]
        or coverage["expected_org_days"] != support["org_weeks"] * 7
        or (
            sealed is not None
            and (
                coverage["period_start"] != sealed["test_start"]
                or coverage["period_end"] != sealed["test_end"]
                or (_day(sealed["test_end"]) - _day(sealed["test_start"])).days + 1
                != support["evaluation_windows"] * 7
            )
        )
    ):
        reasons.append("COVERAGE_EVIDENCE_MISMATCH")
    if any(
        actual < minimum
        for actual, minimum in (
            (support["positive_episodes"], approved_policy["min_positive_episodes"]),
            (support["organizations"], approved_policy["min_organizations"]),
            (support["evaluation_windows"], approved_policy["min_evaluation_windows"]),
        )
    ):
        reasons.append("INSUFFICIENT_SAMPLE_SUPPORT")
    counts = validated_report["counts"]
    model_mae = validated_report["forecast_metrics"]["mae"]
    baseline_mae = validated_report["baseline_metrics"]["mae"]
    false_alert_rate = validated_report["false_alerts_per_org_week"]
    if (
        not counts["tp"] + counts["fp"]
        or not counts["tp"] + counts["fn"]
        or any(
            value is None
            for value in (
                model_mae,
                baseline_mae,
                validated_report["forecast_metrics"]["wape"],
                validated_report["baseline_metrics"]["wape"],
            )
        )
    ):
        reasons.append("UNDEFINED_QUALITY_METRIC")
    if reasons:
        return result("INSUFFICIENT_DATA", reasons)
    # Undefined metrics returned above. Nonzero counts also prove nonzero weeks;
    # report validation binds false-alert rate to that denominator.
    assert model_mae is not None and baseline_mae is not None
    assert false_alert_rate is not None
    if counts["tp"] / (counts["tp"] + counts["fp"]) < approved_policy["min_precision"]:
        reasons.append("PRECISION_BELOW_MINIMUM")
    if counts["tp"] / (counts["tp"] + counts["fn"]) < approved_policy["min_recall"]:
        reasons.append("RECALL_BELOW_MINIMUM")
    if false_alert_rate > approved_policy["max_false_alerts_per_org_week"]:
        reasons.append("FALSE_ALERT_BUDGET_EXCEEDED")
    if model_mae > baseline_mae * approved_policy["max_forecast_error_vs_baseline"]:
        reasons.append("FORECAST_BASELINE_GATE_FAILED")
    return result("FAIL" if reasons else "PASS", reasons)
