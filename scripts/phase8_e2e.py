"""Authenticated Phase 8 acceptance flow against a running isolated stack."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
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


def acknowledge_race(
    client: httpx.Client, api: str, tokens: tuple[str, str], signal: dict[str, Any]
) -> dict[str, Any]:
    """Two distinct identities submit the same version; only one may commit."""
    if tokens[0] == tokens[1]:
        raise ValueError("Race acceptance requires two distinct identities")

    def submit(token: str) -> httpx.Response:
        return client.post(
            f"{api}/signals/{signal['id']}/acknowledge",
            headers={"Authorization": f"Bearer {token}"},
            json={"version": signal["version"], "reason": "Synthetic acceptance race"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(submit, tokens))
    if sorted(response.status_code for response in responses) != [200, 409]:
        raise RuntimeError("Acknowledgement race must have one success and one conflict")
    return dict(
        next(response.json() for response in responses if response.status_code == 200)
    )


def _login(client: httpx.Client, base: str, username: str, password: str) -> str:
    response = client.post(
        f"{base}/auth/realms/medsignal/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "medsignal-frontend",
            "username": username,
            "password": password,
        },
    )
    if response.status_code != 200:
        raise RuntimeError("OIDC acceptance login failed")
    return str(response.json()["access_token"])


def run(base: str) -> dict[str, Any]:
    username = os.environ["PHASE8_TEST_USERNAME"]
    password = os.environ["PHASE8_TEST_PASSWORD"]
    with httpx.Client(timeout=30.0) as client:
        token = _login(client, base, username, password)
        peer_user = os.environ["PHASE8_PEER_USERNAME"]
        if peer_user == username:
            raise ValueError("Race acceptance requires two distinct identities")
        peer = _login(client, base, peer_user, os.environ["PHASE8_PEER_PASSWORD"])
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

        acknowledged = acknowledge_race(client, api, (token, peer), selected)
        ack_audit = _request(
            client,
            "GET",
            f"{api}/audit?entity_id={selected['id']}&action=SIGNAL_ACKNOWLEDGED",
            token,
        )
        if ack_audit["total"] != 1:
            raise RuntimeError("Acknowledgement must create exactly one audit event")
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
        saved_payload = {**scenario_payload, "client_request_id": str(uuid.uuid4())}
        scenario = _request(client, "POST", f"{api}/scenarios", token, json=saved_payload)
        retried = _request(client, "POST", f"{api}/scenarios", token, json=saved_payload)
        if retried["id"] != scenario["id"]:
            raise RuntimeError("Scenario retry duplicated saved result")
        # A fresh HTTP read proves persistence across client refresh, not process restart.
        refreshed = _request(client, "GET", f"{api}/incidents/{incident['id']}", token)
        if refreshed["status"] != "CLOSED":
            raise RuntimeError("Incident refresh lost state")
        scenario_audit = _request(
            client,
            "GET",
            f"{api}/audit?entity_id={scenario['id']}&action=SCENARIO_CREATED",
            token,
        )
        if scenario_audit["total"] != 1:
            raise RuntimeError("Scenario retry must not duplicate audit")
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
        "race": "PASS",
        "scenario_retry": "PASS",
        "client_refresh": "PASS",
        "server_restart": "NOT TESTED",
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
