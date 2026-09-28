"""Fail-closed review of official MinIO advisories before synthetic startup.

Only advisory metadata is saved. GitHub credentials and raw network errors are
never printed or written to acceptance evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from scripts.operations.minio_source_build import (
    BUILD_ROOT,
    CONTRACT_PATH,
    validate_build_contract,
)
from scripts.operations.prepare_acceptance import validate_project_name

ROOT = Path(__file__).resolve().parents[2]
REVIEW_PATH = ROOT / "infrastructure/acceptance/minio-advisory-review.json"
API_URL = "https://api.github.com/repos/minio/minio/security-advisories?per_page=100"
REVIEWED_CRITICAL = {
    "GHSA-cwq8-g58r-32hg": "FIXED BY BACKPORT",
    "GHSA-6xvq-wj2x-3h3q": "NOT AFFECTED",
    "GHSA-2pxw-r47w-4p8c": "NOT AFFECTED",
    "GHSA-w23q-4hw3-2pp6": "NOT AFFECTED",
}


def _fingerprint(advisory: dict[str, Any]) -> dict[str, Any]:
    return {
        "advisory": advisory["ghsa_id"],
        "cve": advisory.get("cve_id"),
        "severity": advisory["severity"].upper(),
        "affected_ranges": [
            {
                "affected_range": row.get("vulnerable_version_range"),
                "fixed_version": row.get("patched_versions"),
            }
            for row in advisory.get("vulnerabilities", [])
        ],
        "description_sha256": hashlib.sha256(
            advisory["description"].encode("utf-8")
        ).hexdigest(),
    }


def check_review(
    reviewed: dict[str, Any], current: list[dict[str, Any]]
) -> dict[str, Any]:
    """Fail on any unreviewed or modified advisory, or remaining critical."""
    expected = {row["advisory"]: row for row in reviewed["advisories"]}
    actual = {row["ghsa_id"]: _fingerprint(row) for row in current}
    if len(expected) != len(reviewed["advisories"]) or len(actual) != len(current):
        raise ValueError("Duplicate MinIO security advisory")
    if set(expected) != set(actual):
        raise ValueError("MinIO advisory set changed; review required")
    for name, row in expected.items():
        if any(actual[name][field] != row[field] for field in actual[name]):
            raise ValueError("MinIO advisory metadata changed; review required")
        status = row["status"]
        if status not in ("NOT AFFECTED", "FIXED BY BACKPORT", "AFFECTED"):
            raise ValueError("Unknown MinIO advisory applicability")
        if row["severity"] == "CRITICAL" and status == "AFFECTED":
            raise ValueError("Remaining critical MinIO advisory")
    backports = [row for row in expected.values() if row["status"] == "FIXED BY BACKPORT"]
    if len(backports) != 1 or backports[0]["advisory"] != "GHSA-cwq8-g58r-32hg":
        raise ValueError("MinIO security backport review changed")
    critical = {
        name: row["status"]
        for name, row in expected.items()
        if row["severity"] == "CRITICAL"
    }
    if critical != REVIEWED_CRITICAL:
        raise ValueError("MinIO critical advisory review changed")
    return {
        "reviewed_count": len(expected),
        "affected_noncritical_count": sum(
            row["status"] == "AFFECTED" for row in expected.values()
        ),
        "critical_remaining": 0,
        "unknown_remaining": 0,
        "security_admission": "FAIL",  # Known HIGH advisories remain.
        "synthetic_functional_review": "PASS",
    }


def fetch_current() -> list[dict[str, Any]]:
    """Read public advisory API; a missing/incomplete response blocks startup."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "medsignal-acceptance",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(API_URL, headers=headers)
    with urlopen(request, timeout=30) as response:  # noqa: S310 — fixed GitHub URL
        data = response.read(2_000_000)
        if response.read(1):
            raise ValueError("MinIO advisory response too large")
    parsed = json.loads(data)
    if not isinstance(parsed, list) or len(parsed) >= 100:
        raise ValueError("MinIO advisory listing incomplete")
    return parsed


def run(project: str) -> dict[str, Any]:
    """Check current advisory metadata and save only sanitized gate result."""
    validate_project_name(project)
    manifest = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    validate_build_contract(manifest)
    reviewed = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    if (
        reviewed["base_commit"] != manifest["server"]["commit_sha"]
        or reviewed["backport_commit"]
        != manifest["server_security_backport"]["fix_commit_sha"]
    ):
        raise ValueError("Advisory review is not for this source/backport")
    result = check_review(reviewed, fetch_current())
    output = BUILD_ROOT / project
    output.mkdir(parents=True, exist_ok=True)
    (output / "advisory-gate.json").write_text(
        json.dumps({"project": project, **result}, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        result = run(args.project)
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError):
        print(
            "MinIO advisory gate: BLOCKED (review unavailable or changed)",
            file=sys.stderr,
        )
        return 2
    print(
        "MinIO advisory gate: PASS for isolated synthetic acceptance; "
        f"{result['affected_noncritical_count']} noncritical advisories remain"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
