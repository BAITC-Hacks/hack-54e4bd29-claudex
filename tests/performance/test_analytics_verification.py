"""Synthetic response contracts for the read-only analytics verifier."""

from __future__ import annotations

import json
import sys
from copy import deepcopy

import httpx
import pytest

from scripts.performance import verify_analytics
from scripts.performance.verify_analytics import (
    VerificationContractError,
    verify_aggregates,
)


def responses() -> tuple[dict, dict, dict]:
    meta = {
        "date_from": "2025-01-01T00:00:00Z",
        "date_to": "2025-01-02T23:59:59Z",
        "latest_import_ids": ["synthetic-import-1"],
        "latest_import_completed_at": "2025-01-03T00:00:00Z",
        "mapping_version": "synthetic-mapping-1",
    }
    overview = {
        "meta": dict(meta),
        "data": {
            "referrals_total": {"value": 5, "suppressed": False},
            "refusals_total": {"value": 3, "suppressed": False},
        },
    }
    referrals = {
        "meta": dict(meta, granularity="DAY"),
        "data": {
            "points": [
                {"period": "2025-01-01", "value": {"value": 2, "suppressed": False}},
                {"period": "2025-01-02", "value": {"value": 3, "suppressed": False}},
            ]
        },
    }
    refusals = {
        "meta": dict(meta, granularity="DAY"),
        "data": {
            "points": [
                {"period": "2025-01-01", "value": {"value": 1, "suppressed": False}},
                {"period": "2025-01-02", "value": {"value": 2, "suppressed": False}},
            ]
        },
    }
    return overview, referrals, refusals


def test_matching_daily_series_are_verified_without_raw_rows() -> None:
    result = verify_aggregates(*responses())

    assert result["status"] == "PASS"
    assert result["checks"] == {
        "referrals": {"status": "PASS", "overview": 5, "daily_sum": 5},
        "refusals": {"status": "PASS", "overview": 3, "daily_sum": 3},
    }
    assert "synthetic-import-1" in result["provenance"]["latest_import_ids"]
    assert result["provenance"]["latest_import_completed_at"] == "2025-01-03T00:00:00Z"


def test_mismatch_fails_with_exact_aggregate_difference() -> None:
    overview, referrals, refusals = responses()
    referrals["data"]["points"][1]["value"]["value"] = 4

    result = verify_aggregates(overview, referrals, refusals)

    assert result["status"] == "FAIL"
    assert result["checks"]["referrals"] == {
        "status": "FAIL",
        "overview": 5,
        "daily_sum": 6,
    }
    assert result["checks"]["refusals"]["status"] == "PASS"


def test_publication_or_period_change_fails_closed_before_comparison() -> None:
    overview, referrals, refusals = responses()
    refusals["meta"]["latest_import_ids"] = ["other-import"]

    result = verify_aggregates(overview, referrals, refusals)

    assert result["status"] == "FAIL"
    assert result["reason"] == "PUBLICATION_OR_PERIOD_MISMATCH"
    assert result["checks"] == {}

    refusals = deepcopy(responses()[2])
    refusals["meta"]["date_to"] = "2025-01-03T23:59:59Z"
    assert verify_aggregates(overview, referrals, refusals)["status"] == "FAIL"


def test_suppressed_or_null_metrics_are_not_interpreted_as_zero() -> None:
    overview, referrals, refusals = responses()
    overview["data"]["referrals_total"] = {"value": None, "suppressed": True}
    refusals["data"]["points"][0]["value"] = {"value": None, "suppressed": False}

    result = verify_aggregates(overview, referrals, refusals)

    assert result["status"] == "NOT TESTED"
    assert result["checks"]["referrals"]["status"] == "NOT TESTED"
    assert result["checks"]["refusals"]["status"] == "NOT TESTED"


def test_duplicate_day_or_wrong_granularity_is_rejected() -> None:
    overview, referrals, refusals = responses()
    referrals["data"]["points"][1]["period"] = "2025-01-01"

    result = verify_aggregates(overview, referrals, refusals)

    assert result["status"] == "FAIL"
    assert result["checks"]["referrals"]["reason"] == "DUPLICATE_PERIOD"

    referrals = deepcopy(responses()[1])
    referrals["meta"]["granularity"] = "WEEK"
    assert verify_aggregates(overview, referrals, refusals)["status"] == "FAIL"


def test_without_published_imports_is_not_a_success() -> None:
    overview, referrals, refusals = responses()
    for response in (overview, referrals, refusals):
        response["meta"]["latest_import_ids"] = []

    assert verify_aggregates(overview, referrals, refusals)["status"] == "NOT TESTED"


def test_waiting_snapshot_and_organization_metadata_share_publication() -> None:
    overview, referrals, refusals = responses()
    overview["data"]["waiting_records"] = {"value": 4, "suppressed": False}
    waiting = {
        "meta": dict(overview["meta"]),
        "data": {
            "snapshot_at": "2025-01-02T00:00:00Z",
            "snapshot_semantics_confirmed": True,
            "waiting_records": {"value": 4, "suppressed": False},
        },
    }
    organizations = {
        "meta": dict(overview["meta"]),
        "data": {"items": [], "page": 1, "page_size": 20, "total": 0, "has_next": False},
    }

    result = verify_aggregates(overview, referrals, refusals, waiting, organizations)
    assert result["status"] == "PASS"
    assert result["checks"]["waiting_snapshot"] == {
        "status": "PASS",
        "overview": 4,
        "summary": 4,
        "snapshot_at": "2025-01-02T00:00:00Z",
    }

    waiting["data"]["waiting_records"]["value"] = 5
    mismatched = verify_aggregates(overview, referrals, refusals, waiting, organizations)
    assert mismatched["checks"]["waiting_snapshot"]["status"] == "FAIL"

    waiting["data"]["waiting_records"]["value"] = 4
    organizations["meta"]["mapping_version"] = "different"
    assert (
        verify_aggregates(overview, referrals, refusals, waiting, organizations)["reason"]
        == "PUBLICATION_OR_PERIOD_MISMATCH"
    )


def test_remote_http_is_rejected_before_any_request() -> None:
    with pytest.raises(VerificationContractError):
        verify_analytics._validate_base_url("http://example.com")


def test_cli_uses_only_bounded_gets_and_never_writes_token(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overview, referrals, refusals = responses()
    overview["data"]["waiting_records"] = {"value": 4, "suppressed": False}
    waiting = {
        "meta": dict(overview["meta"]),
        "data": {
            "snapshot_at": "2025-01-02T00:00:00Z",
            "snapshot_semantics_confirmed": True,
            "waiting_records": {"value": 4, "suppressed": False},
        },
    }
    organizations = {
        "meta": dict(overview["meta"]),
        "data": {"items": [], "page": 1, "page_size": 20, "total": 0, "has_next": False},
    }
    bodies = iter((overview, referrals, refusals, waiting, organizations))
    requests: list[tuple[str, list[tuple[str, str]], str]] = []

    class FakeResponse:
        content = b"synthetic aggregate"

        def __init__(self, body: dict) -> None:
            self.body = body

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return self.body

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 5.0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url: str, *, params, headers) -> FakeResponse:
            requests.append((url, params, headers["Authorization"]))
            return FakeResponse(next(bodies))

    output = tmp_path / "verification.json"
    monkeypatch.setattr(verify_analytics.httpx, "Client", FakeClient)
    monkeypatch.setattr(verify_analytics, "_checkout_sha", lambda: "synthetic-sha")
    monkeypatch.setenv("PERFORMANCE_BEARER_TOKEN", "synthetic-secret-token")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_analytics",
            "--base-url",
            "http://localhost",
            "--date-from",
            "2025-01-01T00:00:00Z",
            "--date-to",
            "2025-01-02T23:59:59Z",
            "--output",
            str(output),
        ],
    )

    assert verify_analytics.main() == 0
    assert [item[0] for item in requests] == [
        "http://localhost/api/v1/analytics/overview",
        "http://localhost/api/v1/analytics/referrals/timeseries",
        "http://localhost/api/v1/analytics/refusals/timeseries",
        "http://localhost/api/v1/analytics/waiting/summary",
        "http://localhost/api/v1/analytics/organizations",
    ]
    assert all(item[2] == "Bearer synthetic-secret-token" for item in requests)
    assert all(len(item[1]) <= 3 for item in requests)
    assert "synthetic-secret-token" not in output.read_text(encoding="utf-8")
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "PASS"
    assert len(saved["filter_digest"]) == 64
    assert saved["provenance"]["latest_import_completed_at"] == "2025-01-03T00:00:00Z"


def test_cli_records_http_status_without_error_body_or_token(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 5.0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url: str, *, params, headers) -> httpx.Response:
            assert params
            assert headers["Authorization"] == "Bearer synthetic-secret-token"
            return httpx.Response(
                503,
                text="sensitive-body-do-not-save",
                request=httpx.Request("GET", url),
            )

    output = tmp_path / "failed.json"
    monkeypatch.setattr(verify_analytics.httpx, "Client", FakeClient)
    monkeypatch.setattr(verify_analytics, "_checkout_sha", lambda: "synthetic-sha")
    monkeypatch.setenv("PERFORMANCE_BEARER_TOKEN", "synthetic-secret-token")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_analytics",
            "--base-url",
            "http://localhost",
            "--date-from",
            "2025-01-01T00:00:00Z",
            "--date-to",
            "2025-01-02T23:59:59Z",
            "--output",
            str(output),
        ],
    )

    assert verify_analytics.main() == 1
    report = output.read_text(encoding="utf-8")
    assert '"reason": "HTTP_503"' in report
    assert "sensitive-body-do-not-save" not in report
    assert "synthetic-secret-token" not in report
