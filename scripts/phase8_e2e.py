"""Authenticated Phase 8 acceptance flow against a running isolated stack."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    token: str,
    **kwargs: Any,
) -> dict[str, Any]:
    response = client.request(
        method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
    )
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    return body


def run(base: str) -> dict[str, Any]:
    username = os.environ["PHASE8_TEST_USERNAME"]
    password = os.environ["PHASE8_TEST_PASSWORD"]
    with httpx.Client(timeout=30.0) as client:
        token_response = client.post(
            f"{base}/auth/realms/medsignal/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "medsignal-frontend",
                "username": username,
                "password": password,
            },
        )
        token_response.raise_for_status()
        token = str(token_response.json()["access_token"])
        api = f"{base}/api/v1"

        actor = _request(client, "GET", f"{api}/system/whoami", token)
        overview = _request(client, "GET", f"{api}/analytics/overview", token)
        forecast = _request(client, "GET", f"{api}/forecasts/referrals/latest", token)
        signals = _request(
            client,
            "GET",
            f"{api}/signals?status=NEW&scope_type=GLOBAL&page_size=100",
            token,
        )
        if not signals["items"]:
            raise RuntimeError("No NEW GLOBAL signal available for E2E")
        selected = signals["items"][0]

        acknowledged = _request(
            client,
            "POST",
            f"{api}/signals/{selected['id']}/acknowledge",
            token,
            json={"version": selected["version"], "reason": "Phase 8 acceptance"},
        )
        incident = _request(
            client,
            "POST",
            f"{api}/signals/{selected['id']}/incidents",
            token,
            json={
                "signal_version": acknowledged["version"],
                "title": "Phase 8 acceptance incident",
                "description": "Synthetic operational acceptance object",
            },
        )
        assigned = _request(
            client,
            "POST",
            f"{api}/incidents/{incident['id']}/assign",
            token,
            json={
                "assignee_id": actor["internal_user_id"],
                "version": incident["version"],
            },
        )
        closed = _request(
            client,
            "PATCH",
            f"{api}/incidents/{incident['id']}/status",
            token,
            json={
                "status": "CLOSED",
                "version": assigned["version"],
                "reason": "Phase 8 workflow verified",
            },
        )

        scenario_payload = {
            "scenario_type": "REFERRAL_INFLOW_CHANGE",
            "scope_type": "GLOBAL",
            "baseline_type": "OBSERVED",
            "assumption_value": "0.20",
            "period_start": "2025-01-01",
            "period_end": "2025-03-31",
            "historical_analysis": True,
            "source_signal_id": selected["id"],
            "source_incident_id": incident["id"],
        }
        _request(
            client,
            "POST",
            f"{api}/scenarios/preview",
            token,
            json=scenario_payload,
        )
        scenario = _request(
            client,
            "POST",
            f"{api}/scenarios",
            token,
            json={**scenario_payload, "client_request_id": str(uuid.uuid4())},
        )
        audit = _request(client, "GET", f"{api}/audit?page_size=100", token)

    return {
        "status": "PASS",
        "actor_id": actor["user_id"],
        "overview_generated_at": overview["meta"]["generated_at"],
        "forecast_id": forecast["id"],
        "signal_id": selected["id"],
        "signal_status": acknowledged["status"],
        "incident_id": incident["id"],
        "incident_status": closed["status"],
        "scenario_id": scenario["id"],
        "audit_events_visible": audit["total"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.base_url.rstrip("/"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
