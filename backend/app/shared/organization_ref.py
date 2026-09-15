"""Stable opaque references for source-level organizations."""

from __future__ import annotations

import hashlib


def source_organization_digest(identity_space: str, normalized_value: str) -> str:
    material = f"{identity_space}\x1f{normalized_value}".encode()
    return hashlib.sha256(material).hexdigest()
