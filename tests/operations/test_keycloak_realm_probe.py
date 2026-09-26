"""Regressions for sanitized, non-root Keycloak realm accessibility checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.operations import keycloak_realm_probe as probe


def test_default_image_user_reads_only_when_real_test_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_command(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "1000\n0\n1001 1001 640\n", "")

    monkeypatch.setattr(probe, "_command", fake_command)
    result = probe._read_probe("quay.io/keycloak/keycloak:26.0", tmp_path / "realm.json")

    assert result == {
        "uid": 1000,
        "gid": 0,
        "mount_uid": 1001,
        "mount_gid": 1001,
        "mount_mode": "640",
        "readable": True,
    }
    assert "--user" not in calls[0]
    assert ":ro" not in " ".join(calls[0])  # Docker --mount uses readonly, not :ro
    assert "readonly" in " ".join(calls[0])
    assert "test -r" in " ".join(calls[0])


def test_local_permission_error_is_not_a_read_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        probe,
        "_command",
        lambda *args: subprocess.CompletedProcess(
            args, 1, "1000\n0\n1001 1001 600\n", "fake-secret permission denied"
        ),
    )
    result = probe._read_probe("quay.io/keycloak/keycloak:26.0", tmp_path / "realm.json")
    assert result["readable"] is False
    assert "fake-secret" not in str(result)


def test_unrelated_user_probe_uses_explicit_unprivileged_uid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_command(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, "20001\n20001\n1001 1001 600\n", "")

    monkeypatch.setattr(probe, "_command", fake_command)
    result = probe._read_probe(
        "quay.io/keycloak/keycloak:26.0", tmp_path / "realm.json", other_user=True
    )
    assert result["readable"] is False
    assert calls[0][calls[0].index("--user") + 1] == "20001:20001"


@pytest.mark.parametrize(
    ("logs", "readable", "http_status", "expected"),
    [
        ("fake-secret AccessDeniedException", False, 404, "REALM_FILE_UNREADABLE"),
        ("fake-secret JsonParseException", True, None, "REALM_PARSE_FAILED"),
        ("fake-secret", True, 404, "REALM_NOT_IMPORTED"),
        ("fake-secret", True, 200, "OIDC_DISCOVERY_OK"),
    ],
)
def test_startup_category_never_reproduces_raw_logs(
    logs: str, readable: bool, http_status: int | None, expected: str
) -> None:
    category = probe._startup_category(
        logs, readable=readable, discovery_status=http_status
    )
    assert category == expected
    assert "fake-secret" not in category


def test_browser_acceptance_waits_for_cheap_realm_preflight() -> None:
    workflow = (
        Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"
    ).read_text(encoding="utf-8")
    assert "keycloak-realm-access:" in workflow
    assert "needs: keycloak-realm-access" in workflow
    assert workflow.index("keycloak-realm-access:") < workflow.index(
        "browser-acceptance:"
    )
