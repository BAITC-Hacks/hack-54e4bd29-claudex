"""Check the real OIDC -> FastAPI -> Copilot path without printing secrets or LLM text.

Default mode is read-only preflight. A paid request requires --paid-test and
separate human approval. No response, prompt, bearer token or credentials are
persisted or printed.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.copilot import ExplainSignalResponse  # noqa: E402

EXPECTED_MODEL = "gpt-4.1-mini-2025-04-14"
QUANTITATIVE = re.compile(
    r"\d|%|процент|п\.\s*п\.|\b(?:ноль|один|одна|два|две|три|"
    r"четыре|пять|шесть|семь|восемь|девять|десять)\b",
    re.IGNORECASE,
)
TEMPORAL = re.compile(r"сегодня|сейчас|текущ[а-я]*|\b20\d\d\b", re.IGNORECASE)
CAUSAL_CLAIM = re.compile(
    r"\b(?:вызван[а-я]*|спровоцирован[а-я]*|обусловлен[а-я]*|"
    r"доказан[а-я]*|гарантирован[а-я]*|рекоменду[а-я]*)\b",
    re.IGNORECASE,
)


def _project(project_dir: Path) -> tuple[str, str, dict[str, Any]]:
    manifest = json.loads((project_dir / "manifest.json").read_text(encoding="utf-8"))
    realm = json.loads((project_dir / "realm.json").read_text(encoding="utf-8"))
    origin = manifest["origin"]
    project = manifest["project"]
    if not re.fullmatch(r"http://127\.0\.0\.1:\d+", origin) or not re.fullmatch(
        r"phase8-[a-z0-9-]+", project
    ):
        raise ValueError("Only loopback phase8 synthetic acceptance is supported")
    return origin, project, realm


def _token(client: httpx.Client, realm: dict[str, Any]) -> str:
    admin = next(user for user in realm["users"] if user["username"] == "admin")
    response = client.post(
        "/auth/realms/medsignal/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "medsignal-frontend",
            "username": admin["username"],
            "password": admin["credentials"][0]["value"],
        },
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def _synthetic_detail(client: httpx.Client, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get("/api/v1/signals", params={"page_size": 100}, headers=headers)
    response.raise_for_status()
    items = response.json()["items"]
    for item in items:
        if item.get("type") != "QUEUE_GROWTH":
            continue
        detail_response = client.get(f"/api/v1/signals/{item['id']}", headers=headers)
        detail_response.raise_for_status()
        detail = detail_response.json()
        if (
            detail.get("source") == "SYNTHETIC_DEV_SEED"
            and detail.get("rule_version") == "seed-0.1"
            and detail.get("rule_config", {}).get("synthetic") is True
            and detail.get("evidence", {}).get("synthetic") is True
            and detail.get("data_watermark", {}).get("synthetic") is True
            and detail.get("explanation", {}).get("generator_version") == "seed-0.1"
            and any(
                isinstance(factor, dict)
                and factor.get("metric_code") in {"queue_size", "incoming_referrals"}
                and isinstance(factor.get("change_pct"), int | float)
                for factor in detail["explanation"].get("factors", [])
            )
        ):
            return detail
    raise ValueError("No eligible synthetic signal with validated facts was found")


def _usage(project: str, request_id: str) -> dict[str, int | None]:
    # Never emit raw Docker logs: only select bounded numeric fields in memory.
    docker = shutil.which("docker")
    if docker is None:
        return {"input_tokens": None, "output_tokens": None}
    try:
        result = subprocess.run(  # noqa: S603 - validated project, fixed argv
            [docker, "logs", "--since", "2m", f"{project}-backend-1"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"input_tokens": None, "output_tokens": None}
    if result.returncode != 0:
        return {"input_tokens": None, "output_tokens": None}
    for line in reversed(result.stdout.splitlines()):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if (
            row.get("request_id") != request_id
            or row.get("message") != "copilot provider completed"
        ):
            continue
        return {
            output: row[source] if type(row.get(source)) is int else None
            for output, source in (
                ("input_tokens", "input_usage_count"),
                ("output_tokens", "output_usage_count"),
            )
        }
    return {"input_tokens": None, "output_tokens": None}


def _validate_response(body: dict[str, Any], detail: dict[str, Any]) -> dict[str, bool]:
    parsed = ExplainSignalResponse.model_validate(body)
    fact_ids = {fact.id for fact in parsed.facts}
    facts_valid = (
        bool(fact_ids) and bool(parsed.fact_ids) and set(parsed.fact_ids) <= fact_ids
    )
    provenance_valid = (
        str(parsed.signal_id) == detail["id"]
        and parsed.signal_version == detail["version"]
        and parsed.provider == "openai"
        and parsed.model == EXPECTED_MODEL
        and parsed.llm_generated is True
    )
    chronology_valid = all(
        fact.period_start is None
        or fact.period_end is None
        or fact.period_start <= fact.period_end
        for fact in parsed.facts
    )
    explanation = detail.get("explanation") or {}
    expected_factors = [
        factor
        for factor in explanation.get("factors", [])[:8]
        if factor.get("metric_code")
        in {"queue_size", "incoming_referrals", "refusal_rate", "composite_deviation"}
        and type(factor.get("change_pct")) in {int, float}
        and math.isfinite(factor["change_pct"])
        and abs(factor["change_pct"]) <= 1000
        and factor.get("direction") in {"INCREASE", "DECREASE"}
    ]
    input_start = explanation.get("input_period_start")
    input_end = explanation.get("input_period_end")
    facts_match_server = len(parsed.facts) == len(expected_factors) and all(
        fact.id == f"F{index + 1}"
        and fact.metric_code == factor["metric_code"]
        and fact.value == float(factor["change_pct"])
        and fact.direction == factor["direction"]
        and fact.unit == "percent_change"
        and fact.source == "signal_explanation"
        and fact.period_start
        == (datetime.fromisoformat(input_start) if input_start else None)
        and fact.period_end == (datetime.fromisoformat(input_end) if input_end else None)
        for index, (fact, factor) in enumerate(
            zip(parsed.facts, expected_factors, strict=True)
        )
    )
    no_unchecked_claims = not any(
        pattern.search(parsed.explanation)
        for pattern in (QUANTITATIVE, TEMPORAL, CAUSAL_CLAIM)
    )
    limitations_valid = (
        parsed.data_current is False
        and parsed.data_watermark_at is None
        and len(parsed.limitations) >= 3
        and any("Синтетическ" in item for item in parsed.limitations)
        and any("текущ" in item for item in parsed.limitations)
    )
    nulls_valid = all(
        getattr(parsed, name) is None or detail.get(name) is not None
        for name in (
            "evaluation_period_start",
            "evaluation_period_end",
            "reference_period_start",
            "reference_period_end",
        )
    )
    return {
        "schema": True,
        "fact_ids": facts_valid,
        "facts_match_server": facts_match_server,
        "provenance": provenance_valid,
        "fact_periods": chronology_valid,
        "no_unchecked_text_claims": no_unchecked_claims,
        "synthetic_historical_limitations": limitations_valid,
        "unknown_dates_preserved": nulls_valid,
    }


def verify(project_dir: Path, *, paid_test: bool) -> dict[str, Any]:
    origin, project, realm = _project(project_dir)
    with httpx.Client(base_url=origin, timeout=40) as client:
        token = _token(client, realm)
        headers = {"Authorization": f"Bearer {token}"}
        detail = _synthetic_detail(client, headers)
        openapi = client.get("/api/v1/openapi.json")
        openapi.raise_for_status()
        route_present = "/api/v1/copilot/explain-signal" in openapi.json().get(
            "paths", {}
        )
        if not paid_test:
            return {
                "live_llm_verification": "NOT TESTED",
                "real_oidc": True,
                "eligible_synthetic_signal": True,
                "copilot_route_present": route_present,
            }
        if not route_present:
            raise ValueError(
                "Copilot route is absent; backend overlay must be started first"
            )

        started = time.monotonic()
        response = client.post(
            "/api/v1/copilot/explain-signal",
            json={"signal_id": detail["id"]},
            headers=headers,
        )
        duration_ms = round((time.monotonic() - started) * 1000)
        request_id = response.headers.get("x-request-id")
        result: dict[str, Any] = {
            "http_status": response.status_code,
            "provider": "openai",
            "model": EXPECTED_MODEL,
            "duration_ms": duration_ms,
            "request_id": request_id,
            "live_llm_verification": "FAIL",
        }
        if response.status_code != 200:
            try:
                result["error_code"] = response.json().get("error", {}).get("code")
            except ValueError:
                result["error_code"] = "NON_JSON_ERROR"
            return result
        checks = _validate_response(response.json(), detail)
        result["checks"] = checks
        result.update(_usage(project, request_id or ""))
        result["live_llm_verification"] = "PASS" if all(checks.values()) else "FAIL"
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument(
        "--paid-test", action="store_true", help="Send exactly one billable API request"
    )
    args = parser.parse_args()
    try:
        result = verify(args.project_dir, paid_test=args.paid_test)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if result["live_llm_verification"] == "FAIL":
            raise SystemExit(1)
    except (OSError, ValueError, KeyError, httpx.HTTPError) as exc:
        # Do not emit exception text: HTTP clients and parsers may include credentials.
        print(
            json.dumps(
                {"live_llm_verification": "FAIL", "failure_category": type(exc).__name__}
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
