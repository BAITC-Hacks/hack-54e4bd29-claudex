"""Exercise real signed OIDC identities against synthetic mapped analytics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

PERIOD = ("2025-01-01T00:00:00Z", "2025-01-03T23:59:59Z")


def _counts(response: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    cells = response["data"]
    return (
        cells["referrals_total"]["value"],
        cells["waiting_records"]["value"],
        cells["refusals_total"]["value"],
    )


def verify(project_dir: Path) -> dict[str, Any]:
    """Check global, regional and hospital scope with real test tokens."""
    manifest = json.loads((project_dir / "manifest.json").read_text(encoding="utf-8"))
    realm = json.loads((project_dir / "realm.json").read_text(encoding="utf-8"))
    origin = manifest["origin"]
    if not origin.startswith("http://127.0.0.1:") or not manifest["project"].startswith(
        "phase8-"
    ):
        raise ValueError("Only loopback phase8 acceptance project is supported")
    users = {item["username"]: item for item in realm["users"]}
    params = {"date_from": PERIOD[0], "date_to": PERIOD[1]}
    with httpx.Client(base_url=origin, timeout=15) as client:
        tokens: dict[str, str] = {}
        for name in ("admin", "regional-analyst", "hospital-manager"):
            response = client.post(
                "/auth/realms/medsignal/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": "medsignal-frontend",
                    "username": name,
                    "password": users[name]["credentials"][0]["value"],
                },
            )
            response.raise_for_status()
            tokens[name] = response.json()["access_token"]

        def get(name: str, route: str, extra: dict[str, str] | None = None) -> dict:
            response = client.get(
                route,
                params={**params, **(extra or {})}
                if route.startswith("/api/v1/analytics")
                else None,
                headers={"Authorization": f"Bearer {tokens[name]}"},
            )
            response.raise_for_status()
            return response.json()

        regions = {
            item["code"]: item["id"] for item in get("admin", "/api/v1/regions")["items"]
        }
        hospitals = {
            item["code"]: item["id"]
            for item in get("admin", "/api/v1/hospitals")["items"]
        }
        hospital_ref = f"canonical:{hospitals['H-A1']}"
        expected = {
            "admin": (30, 22, 24),
            "regional-analyst": (15, 11, 12),
            "hospital-manager": (15, 11, 12),
        }
        actual = {
            name: _counts(get(name, "/api/v1/analytics/overview")) for name in expected
        }
        intersection = _counts(
            get(
                "admin",
                "/api/v1/analytics/overview",
                {"region": regions["R-A"], "organization": hospital_ref},
            )
        )
        disjoint = _counts(
            get(
                "admin",
                "/api/v1/analytics/overview",
                {"region": regions["R-B"], "organization": hospital_ref},
            )
        )
        foreign: tuple[int | None, int | None, int | None] | str
        try:
            foreign = _counts(
                get(
                    "hospital-manager",
                    "/api/v1/analytics/overview",
                    {"organization": f"canonical:{hospitals['H-B1']}"},
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            foreign = "404"
    result = {
        "counts": actual,
        "region_organization_intersection": intersection,
        "disjoint_intersection": disjoint,
        "foreign_hospital_filter": foreign,
    }
    if (
        actual != expected
        or intersection != expected["hospital-manager"]
        or disjoint != (0, 0, 0)
        or foreign not in {(0, 0, 0), "404"}
    ):
        raise AssertionError(f"Synthetic scoped analytics mismatch: {result}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path)
    result = verify(parser.parse_args().project_dir)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
