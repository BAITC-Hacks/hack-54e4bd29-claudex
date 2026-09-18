"""Real signed-token acceptance for the local development realm.

The test is opt-in because it requires the running Compose stack. It never
prints access tokens and uses only synthetic development identities.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_KEYCLOAK_TESTS") != "1",
    reason="set RUN_REAL_KEYCLOAK_TESTS=1 against the local Compose stack",
)

BASE = os.getenv("MEDSIGNAL_BASE_URL", "http://localhost")
TOKEN_URL = f"{BASE}/auth/realms/medsignal/protocol/openid-connect/token"

IDENTITIES = {
    "health-authority": (
        "health-authority-local_dev_only",
        "HEALTH_AUTHORITY",
        True,
        {"H-A1", "H-A2", "H-B1"},
    ),
    "regional-analyst": (
        "regional-analyst-local_dev_only",
        "REGIONAL_ANALYST",
        False,
        {"H-A1", "H-A2"},
    ),
    "hospital-manager": (
        "hospital-manager-local_dev_only",
        "HOSPITAL_MANAGER",
        False,
        {"H-A1"},
    ),
}


def _token(client: httpx.Client, username: str, password: str) -> str:
    response = client.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": "medsignal-frontend",
            "username": username,
            "password": password,
        },
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def _get(client: httpx.Client, token: str, path: str) -> httpx.Response:
    return client.get(
        f"{BASE}/api/v1{path}", headers={"Authorization": f"Bearer {token}"}
    )


def test_real_tokens_map_roles_and_enforce_scope() -> None:
    with httpx.Client(timeout=15.0) as client:
        tokens = {
            username: _token(client, username, details[0])
            for username, details in IDENTITIES.items()
        }

        visible: dict[str, dict[str, str]] = {}
        for username, (
            _,
            expected_role,
            global_scope,
            expected_codes,
        ) in IDENTITIES.items():
            token = tokens[username]
            whoami = _get(client, token, "/system/whoami")
            assert whoami.status_code == 200
            context = whoami.json()
            assert expected_role in context["roles"]
            assert context["has_global_scope"] is global_scope
            assert context["scope_resolved"] is True

            hospitals = _get(client, token, "/hospitals?page_size=100")
            assert hospitals.status_code == 200
            items = hospitals.json()["items"]
            visible[username] = {item["code"]: item["id"] for item in items}
            assert set(visible[username]) == expected_codes

        global_hospitals = visible["health-authority"]
        assert (
            _get(
                client,
                tokens["regional-analyst"],
                f"/hospitals/{global_hospitals['H-B1']}",
            ).status_code
            == 404
        )
        assert (
            _get(
                client,
                tokens["hospital-manager"],
                f"/hospitals/{global_hospitals['H-A2']}",
            ).status_code
            == 404
        )
