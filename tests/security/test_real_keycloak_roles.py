"""Opt-in real signed tokens; isolated realm credentials come only from environment."""

from __future__ import annotations

import os

import httpx
import pytest

from scripts.security.acceptance_identities import AcceptanceIdentity, load_identities

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_KEYCLOAK_TESTS") != "1",
    reason="requires isolated stack and MEDSIGNAL_TEST_IDENTITIES",
)
BASE = os.getenv("MEDSIGNAL_BASE_URL", "http://localhost")
TOKEN_URL = f"{BASE}/auth/realms/medsignal/protocol/openid-connect/token"


def _token(client: httpx.Client, identity: AcceptanceIdentity) -> str:
    response = client.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": "medsignal-frontend",
            "username": identity.username,
            "password": identity.password,
        },
    )
    assert response.status_code == 200, "OIDC token acquisition failed"
    return str(response.json()["access_token"])


def _get(client: httpx.Client, token: str, path: str) -> httpx.Response:
    return client.get(
        f"{BASE}/api/v1{path}", headers={"Authorization": f"Bearer {token}"}
    )


def test_real_tokens_map_roles_and_enforce_scope() -> None:
    identities = load_identities()
    assert {item.role for item in identities} == {
        "ADMIN",
        "HEALTH_AUTHORITY",
        "REGIONAL_ANALYST",
        "HOSPITAL_MANAGER",
        "HOSPITAL_ANALYST",
    }, "Acceptance requires all five roles"
    assert any(
        item.role == "HEALTH_AUTHORITY" and not item.global_scope for item in identities
    )
    with httpx.Client(timeout=15.0) as client:
        tokens = {item.username: _token(client, item) for item in identities}
        visible: dict[str, dict[str, str]] = {}
        for identity in identities:
            token = tokens[identity.username]
            whoami = _get(client, token, "/system/whoami")
            assert whoami.status_code == 200
            context = whoami.json()
            assert identity.role in context["roles"]
            assert context["has_global_scope"] is identity.global_scope
            assert context["scope_resolved"] is True
            hospitals = _get(client, token, "/hospitals?page_size=100")
            assert hospitals.status_code == 200
            rows = hospitals.json()["items"]
            visible[identity.username] = {row["code"]: row["id"] for row in rows}
            assert set(visible[identity.username]) == identity.hospital_codes
            if not identity.global_scope:
                forecast = _get(client, token, "/forecasts/referrals/latest")
                assert forecast.status_code == 404
                signals = _get(client, token, "/signals?scope_type=GLOBAL")
                assert signals.status_code == 200
                assert signals.json()["total"] == 0
        known = {
            code: identifier
            for rows in visible.values()
            for code, identifier in rows.items()
        }
        for identity in identities:
            for code, identifier in known.items():
                if code not in identity.hospital_codes:
                    assert (
                        _get(
                            client, tokens[identity.username], f"/hospitals/{identifier}"
                        ).status_code
                        == 404
                    )
        # Invalid bearer cannot use any cached authenticated result.
        assert (
            _get(client, "invalid-token", "/forecasts/referrals/latest").status_code
            == 401
        )
