"""Synthetic regressions for semantic evidence, including the real audit generator."""

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from data_pipeline.audit import cli
from data_pipeline.audit.target_analysis import TableEvidence, assess_candidates


def evidence(**kwargs):
    values = {
        "dataset": "synthetic",
        "table": "events",
        "columns": (
            "registration_dt",
            "hospital_mo",
            "profile",
            "hospitalization_dt",
            "refuse_dt",
        ),
        "row_count": 100,
        "months_covered": 24,
        "granularity": "event-level",
        "time_series_possible": True,
    }
    values.update(kwargs)
    return TableEvidence(**values)


def candidate(key, *tables):
    return next(c for c in assess_candidates(tables) if c.key == key)


@pytest.mark.parametrize("count", [0, 1])
def test_one_snapshot_is_not_queue_forecast_history(count):
    from data_pipeline.audit.target_analysis import assess_temporal_target

    assert assess_temporal_target(
        "queue_size(t+n)",
        verified_snapshot_count=count,
        denominator_aligned=False,
    ) == ("NOT AVAILABLE", "NO_VERIFIED_SNAPSHOT_HISTORY")


def test_refusal_ratio_requires_population_alignment():
    from data_pipeline.audit.target_analysis import assess_temporal_target

    assert assess_temporal_target(
        "refusal_rate",
        verified_snapshot_count=2,
        denominator_aligned=False,
    ) == ("NOT AVAILABLE", "DENOMINATOR_NOT_ALIGNED")


@pytest.mark.parametrize("target", ["queue_size(t+n)", "refusal_rate"])
def test_verified_semantics_still_require_coverage_review(target):
    from data_pipeline.audit.target_analysis import assess_temporal_target

    assert assess_temporal_target(
        target,
        verified_snapshot_count=2,
        denominator_aligned=True,
    ) == ("PARTIALLY AVAILABLE", "REQUIRES_COVERAGE_REVIEW")


def test_unknown_target_fails_closed():
    from data_pipeline.audit.target_analysis import assess_temporal_target

    assert assess_temporal_target(
        "unknown",
        verified_snapshot_count=100,
        denominator_aligned=True,
    ) == ("NOT AVAILABLE", "UNKNOWN_TARGET_SEMANTICS")


@pytest.mark.parametrize(
    "key,reason",
    [
        ("queue_size", "NO_VERIFIED_SNAPSHOT_HISTORY"),
        ("refusal_rate", "DENOMINATOR_NOT_ALIGNED"),
    ],
)
def test_months_and_all_columns_do_not_confirm_semantics(key, reason):
    result = candidate(key, evidence())
    assert result.status == "NOT AVAILABLE"
    assert reason in result.reason
    assert result.feasibility == "NOT FEASIBLE"


@pytest.mark.parametrize(
    "count,proof,status",
    [
        (1, "owner-approved synthetic snapshot manifest", "NOT AVAILABLE"),
        (2, None, "NOT AVAILABLE"),
        (2, " ", "NOT AVAILABLE"),
        (2, "owner-approved synthetic snapshot manifest", "PARTIALLY AVAILABLE"),
    ],
)
def test_only_verified_repeated_snapshots_unlock_review(count, proof, status):
    result = candidate(
        "queue_size",
        evidence(
            verified_snapshot_count=count,
            snapshot_verification=proof,
        ),
    )
    assert result.status == status
    assert result.status != "AVAILABLE"


def test_snapshot_count_cannot_be_borrowed_or_summed_across_tables():
    one = evidence(verified_snapshot_count=1, snapshot_verification="manifest")
    other = replace(one, table="other")
    unrelated = evidence(
        table="unrelated",
        columns=("snapshot_dt",),
        verified_snapshot_count=30,
        snapshot_verification="manifest",
    )
    assert candidate("queue_size", one, other, unrelated).status == "NOT AVAILABLE"


@pytest.mark.parametrize(
    "denominator,proof,status",
    [
        ((), "contract", "NOT AVAILABLE"),
        (("synthetic.events",), None, "NOT AVAILABLE"),
        (("synthetic.events",), " ", "NOT AVAILABLE"),
        (("synthetic.absent",), "contract", "NOT AVAILABLE"),
        (
            ("synthetic.events",),
            "owner-approved population/period/org contract",
            "PARTIALLY AVAILABLE",
        ),
    ],
)
def test_refusal_alignment_requires_present_denominator_and_proof(
    denominator, proof, status
):
    result = candidate(
        "refusal_rate",
        evidence(
            aligned_denominator_tables=denominator,
            denominator_verification=proof,
        ),
    )
    assert result.status == status


def test_verified_cross_table_refusal_ratio_is_only_partial():
    numerator = evidence(
        table="refusals",
        columns=("refuse_dt", "hospital_mo"),
        aligned_denominator_tables=("synthetic.events",),
        denominator_verification="aligned population, period, org and coverage",
    )
    result = candidate("refusal_rate", numerator, evidence())
    assert result.status == "PARTIALLY AVAILABLE"
    assert "REQUIRES_COVERAGE_REVIEW" in result.reason


def test_alignment_on_unrelated_table_cannot_approve_refusals():
    numerator = evidence(table="refusals", columns=("refuse_dt", "hospital_mo"))
    denominator = evidence(
        columns=("registration_dt", "hospital_mo"),
        aligned_denominator_tables=("synthetic.events",),
        denominator_verification="contract",
    )
    assert candidate("refusal_rate", numerator, denominator).status == "NOT AVAILABLE"


@pytest.mark.parametrize("key", ["queue_size", "refusal_rate"])
def test_semantic_proof_cannot_replace_required_columns(key):
    result = candidate(
        key,
        evidence(
            columns=("some_column",),
            verified_snapshot_count=30,
            snapshot_verification="manifest",
            aligned_denominator_tables=("synthetic.events",),
            denominator_verification="contract",
        ),
    )
    assert result.status == "NOT AVAILABLE"


def test_one_snapshot_keeps_descriptive_row_count():
    table = evidence(row_count=100, months_covered=24, granularity="single snapshot")
    candidate("queue_size", table)
    assert table.row_count == 100


def test_cli_does_not_reintroduce_availability_from_dates(
    source_root: Path, tmp_path: Path
):
    # All required columns and a date span exist; no semantic contract exists.
    source = source_root / "Направления" / "Направления.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = [*reader.fieldnames, "refuse_dt", "snapshot_dt"]
    for row in rows:
        row["refuse_dt"] = row["registration_dt"]
        row["snapshot_dt"] = row["registration_dt"]
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    output, docs = tmp_path / "audit", tmp_path / "docs"
    assert (
        cli.main(
            ["--source", str(source_root), "--output", str(output), "--docs", str(docs)]
        )
        == 0
    )
    summary = json.loads(
        (output / "medsignal_audit_summary.json").read_text(encoding="utf-8")
    )
    results = {c["key"]: c for c in summary["target_candidates"]}
    for key in ("queue_size", "refusal_rate"):
        assert results[key]["status"] == "NOT AVAILABLE"
        assert results[key]["feasibility"] == "NOT FEASIBLE"
    for filename in ("TARGET_FEASIBILITY.md", "DATA_AUDIT_REPORT.md"):
        report = (docs / filename).read_text(encoding="utf-8")
        assert "| queue_size(t+n) | NOT AVAILABLE |" in report
        assert "| refusal_rate | NOT AVAILABLE |" in report
