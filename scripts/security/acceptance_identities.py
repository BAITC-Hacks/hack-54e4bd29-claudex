"""Environment-only credentials for opt-in isolated OIDC acceptance."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

ROLES = frozenset(
    {
        "ADMIN",
        "HEALTH_AUTHORITY",
        "REGIONAL_ANALYST",
        "HOSPITAL_MANAGER",
        "HOSPITAL_ANALYST",
    }
)


@dataclass(frozen=True, slots=True)
class AcceptanceIdentity:
    username: str
    password: str = field(repr=False)
    role: str
    global_scope: bool
    hospital_codes: frozenset[str]


def load_identities() -> tuple[AcceptanceIdentity, ...]:
    """No fallback users; invalid values never appear in exception messages."""
    raw = os.environ.get("MEDSIGNAL_TEST_IDENTITIES")
    if not raw:
        raise ValueError("MEDSIGNAL_TEST_IDENTITIES is required for real-token tests")
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError("Invalid acceptance identity configuration") from None
    if not isinstance(payload, list) or not payload or len(payload) > 20:
        raise ValueError("Invalid acceptance identity configuration")
    identities = []
    names: set[str] = set()
    fields = {"username", "password", "role", "global_scope", "hospital_codes"}
    for item in payload:
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError("Invalid acceptance identity configuration")
        if not all(
            isinstance(item[key], str) and item[key].strip()
            for key in ("username", "password", "role")
        ):
            raise ValueError("Invalid acceptance identity configuration")
        codes = item["hospital_codes"]
        if (
            item["role"] not in ROLES
            or type(item["global_scope"]) is not bool
            or not isinstance(codes, list)
            or not all(isinstance(code, str) and code.strip() for code in codes)
            or item["username"] in names
        ):
            raise ValueError("Invalid acceptance identity configuration")
        names.add(item["username"])
        identities.append(
            AcceptanceIdentity(
                item["username"],
                item["password"],
                item["role"],
                item["global_scope"],
                frozenset(codes),
            )
        )
    return tuple(identities)
