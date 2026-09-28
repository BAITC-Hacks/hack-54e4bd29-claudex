"""Official advisory review is a fail-closed synthetic acceptance gate."""

from __future__ import annotations

import copy
import json

import pytest

from scripts.operations import minio_advisory_gate, minio_source_build


def _reviewed() -> dict[str, object]:
    return json.loads(minio_advisory_gate.REVIEW_PATH.read_text(encoding="utf-8"))


def _current(review: dict[str, object]) -> list[dict[str, object]]:
    rows = review["advisories"]
    assert isinstance(rows, list)
    return [
        {
            "ghsa_id": row["advisory"],
            "cve_id": row["cve"],
            "severity": row["severity"].lower(),
            "description": "synthetic-review-text",
            "vulnerabilities": [
                {
                    "vulnerable_version_range": v["affected_range"],
                    "patched_versions": v["fixed_version"],
                }
                for v in row["affected_ranges"]
            ],
        }
        for row in rows
    ]


def test_review_includes_every_current_official_advisory() -> None:
    review = _reviewed()
    rows = review["advisories"]
    assert len(rows) == 27
    assert sum(row["status"] == "AFFECTED" for row in rows) == 10
    assert sum(row["status"] == "FIXED BY BACKPORT" for row in rows) == 1
    assert all(row["status"] != "UNKNOWN" for row in rows)
    assert all(
        row["source_url"].startswith("https://github.com/minio/minio/") for row in rows
    )


def test_new_advisory_or_critical_applicability_blocks_before_start() -> None:
    review = _reviewed()
    current = _current(review)
    for row in review["advisories"]:
        row["description_sha256"] = minio_advisory_gate.hashlib.sha256(
            b"synthetic-review-text"
        ).hexdigest()
    result = minio_advisory_gate.check_review(review, current)
    assert result["critical_remaining"] == 0
    assert result["security_admission"] == "FAIL"
    new = copy.deepcopy(current)
    new.append({**new[0], "ghsa_id": "GHSA-new-unreviewed"})
    with pytest.raises(ValueError, match="set changed"):
        minio_advisory_gate.check_review(review, new)
    broken = copy.deepcopy(review)
    next(row for row in broken["advisories"] if row["advisory"] == "GHSA-cwq8-g58r-32hg")[
        "status"
    ] = "AFFECTED"
    with pytest.raises(ValueError, match="critical"):
        minio_advisory_gate.check_review(broken, current)


def test_review_rejects_changed_body_without_leaking_secret() -> None:
    review = _reviewed()
    current = _current(review)
    for row in review["advisories"]:
        row["description_sha256"] = minio_advisory_gate.hashlib.sha256(
            b"synthetic-review-text"
        ).hexdigest()
    current[0]["description"] = "fake-token-secret"
    with pytest.raises(ValueError, match="metadata changed") as error:
        minio_advisory_gate.check_review(review, current)
    assert "fake-token-secret" not in str(error.value)


def test_backport_edit_comparison_rejects_extra_application_edit() -> None:
    patch = (
        minio_source_build.ROOT
        / "infrastructure/acceptance/patches/server-cve-2024-55949.patch"
    ).read_bytes()
    lines = minio_source_build._edited_lines(patch)
    assert any(
        b"validateAdminReq(ctx, w, r, policy.ImportIAMAction)" in row for row in lines
    )
    assert lines != minio_source_build._edited_lines(patch + b"\n+unapproved edit\n")
