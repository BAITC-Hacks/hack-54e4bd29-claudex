"""Compare published aggregate analytics through the authenticated read-only API.

The report contains aggregate counts and publication metadata only. It never
records a bearer token, response body, source organization or patient value.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

ROUTES = {
    "overview": "/api/v1/analytics/overview",
    "referrals": "/api/v1/analytics/referrals/timeseries",
    "refusals": "/api/v1/analytics/refusals/timeseries",
}
PROVENANCE_KEYS = ("date_from", "date_to", "latest_import_ids", "mapping_version")
MAX_RESPONSE_BYTES = 2_000_000


class VerificationContractError(ValueError):
    """An aggregate response cannot be compared safely."""


def _provenance(response: dict[str, Any]) -> dict[str, Any]:
    meta = response["meta"]
    result = {key: meta[key] for key in PROVENANCE_KEYS}
    if not isinstance(result["latest_import_ids"], list) or not all(
        isinstance(item, str) for item in result["latest_import_ids"]
    ):
        raise VerificationContractError("invalid publication IDs")
    return result


def _cell_value(cell: dict[str, Any]) -> int | None:
    if not isinstance(cell["suppressed"], bool):
        raise VerificationContractError("invalid suppression flag")
    value = cell["value"]
    if cell["suppressed"] or value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise VerificationContractError("invalid aggregate count")
    return value


def _daily_sum(
    series: dict[str, Any], start: date, end: date
) -> tuple[int | None, str | None]:
    if series["meta"]["granularity"] != "DAY":
        return None, "GRANULARITY_NOT_DAY"
    points = series["data"]["points"]
    if not isinstance(points, list) or len(points) > 366:
        raise VerificationContractError("unbounded timeseries")
    seen: set[date] = set()
    total = 0
    missing = False
    for point in points:
        period = datetime.fromisoformat(point["period"].replace("Z", "+00:00")).date()
        if period in seen:
            return None, "DUPLICATE_PERIOD"
        if period < start or period > end:
            return None, "PERIOD_OUTSIDE_FILTER"
        seen.add(period)
        value = _cell_value(point["value"])
        if value is None:
            missing = True
        else:
            total += value
    return (None, "SUPPRESSED_OR_MISSING") if missing else (total, None)


def verify_aggregates(
    overview: dict[str, Any], referrals: dict[str, Any], refusals: dict[str, Any]
) -> dict[str, Any]:
    """Check daily referral/refusal sums against KPI counts at one publication."""
    try:
        provenance = _provenance(overview)
        if any(_provenance(series) != provenance for series in (referrals, refusals)):
            return {
                "status": "FAIL",
                "reason": "PUBLICATION_OR_PERIOD_MISMATCH",
                "checks": {},
            }
        if not provenance["latest_import_ids"]:
            return {
                "status": "NOT TESTED",
                "reason": "NO_PUBLISHED_IMPORTS",
                "checks": {},
            }
        start = datetime.fromisoformat(
            provenance["date_from"].replace("Z", "+00:00")
        ).date()
        end = datetime.fromisoformat(provenance["date_to"].replace("Z", "+00:00")).date()
        checks: dict[str, dict[str, Any]] = {}
        for name, metric, series in (
            ("referrals", "referrals_total", referrals),
            ("refusals", "refusals_total", refusals),
        ):
            expected = _cell_value(overview["data"][metric])
            actual, reason = _daily_sum(series, start, end)
            if reason in {
                "GRANULARITY_NOT_DAY",
                "DUPLICATE_PERIOD",
                "PERIOD_OUTSIDE_FILTER",
            }:
                checks[name] = {"status": "FAIL", "reason": reason}
            elif expected is None or actual is None:
                checks[name] = {"status": "NOT TESTED", "reason": "SUPPRESSED_OR_MISSING"}
            else:
                checks[name] = {
                    "status": "PASS" if expected == actual else "FAIL",
                    "overview": expected,
                    "daily_sum": actual,
                }
    except (KeyError, TypeError, ValueError):
        return {"status": "FAIL", "reason": "INVALID_RESPONSE_CONTRACT", "checks": {}}
    statuses = {check["status"] for check in checks.values()}
    status = (
        "FAIL"
        if "FAIL" in statuses
        else "NOT TESTED"
        if "NOT TESTED" in statuses
        else "PASS"
    )
    return {
        "status": status,
        "checks": checks,
        "provenance": provenance,
    }


def _validate_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (
            parsed.scheme == "http"
            and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        )
    ):
        raise VerificationContractError("HTTPS required outside loopback")
    return base_url.rstrip("/")


def _checkout_sha() -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    command = subprocess.run(  # noqa: S603
        [git, "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return command.stdout.strip() if command.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--region", action="append", default=[])
    parser.add_argument("--organization", action="append", default=[])
    parser.add_argument("--token-env", default="PERFORMANCE_BEARER_TOKEN")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 30:
        parser.error("timeout must be between 1 and 30 seconds")
    try:
        base_url = _validate_base_url(args.base_url)
    except VerificationContractError as exc:
        parser.error(str(exc))
    token = os.getenv(args.token_env)
    if not token:
        parser.error("bearer token environment variable is missing")
    params = [("date_from", args.date_from), ("date_to", args.date_to)]
    params += [("region", item) for item in args.region]
    params += [("organization", item) for item in args.organization]
    try:
        with httpx.Client(timeout=args.timeout) as client:
            responses = {}
            for name, route in ROUTES.items():
                route_params = params + (
                    [("granularity", "DAY")] if name != "overview" else []
                )
                response = client.get(
                    base_url + route,
                    params=route_params,
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                if len(response.content) > MAX_RESPONSE_BYTES:
                    raise VerificationContractError("aggregate response too large")
                responses[name] = response.json()
        report = verify_aggregates(**responses)
    except httpx.HTTPStatusError as exc:
        report = {
            "status": "FAIL",
            "reason": f"HTTP_{exc.response.status_code}",
            "checks": {},
        }
    except httpx.TimeoutException:
        report = {"status": "FAIL", "reason": "CLIENT_TIMEOUT", "checks": {}}
    except httpx.HTTPError:
        report = {"status": "FAIL", "reason": "NETWORK_ERROR", "checks": {}}
    except ValueError:
        report = {"status": "FAIL", "reason": "INVALID_RESPONSE_CONTRACT", "checks": {}}
    report["git_sha"] = _checkout_sha()
    report["filters"] = {
        "date_from": args.date_from,
        "date_to": args.date_to,
        "region_count": len(args.region),
        "organization_count": len(args.organization),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Aggregate verification: {report['status']}; report: {args.output}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
