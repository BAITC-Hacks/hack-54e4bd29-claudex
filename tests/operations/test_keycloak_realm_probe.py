"""Regressions for sanitized, non-root Keycloak realm accessibility checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.operations import keycloak_realm_probe as probe
from scripts.operations import prepare_acceptance


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


def test_realm_acl_grants_only_actual_nonroot_image_uid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    realm = tmp_path / "realm.json"
    realm.write_text("synthetic-secret", encoding="utf-8")
    other_secret = tmp_path / ".env"
    other_secret.write_text("APP_SECRET=unrelated-secret", encoding="utf-8")
    other_mode_before = other_secret.stat().st_mode
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(prepare_acceptance, "_supports_posix_acl", lambda: True)
    monkeypatch.setattr(
        prepare_acceptance.shutil, "which", lambda *_args: "/usr/bin/setfacl"
    )

    def image_info(*args: str, timeout: int = 15) -> subprocess.CompletedProcess[str]:
        assert timeout == 15
        return subprocess.CompletedProcess(args, 0, "sha256:" + "a" * 64 + "|1000", "")

    monkeypatch.setattr(
        prepare_acceptance,
        "_quiet_command",
        image_info,
    )

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(prepare_acceptance.subprocess, "run", fake_run)
    result = prepare_acceptance.grant_keycloak_realm_read(
        "quay.io/keycloak/keycloak:26.0", realm
    )

    assert result["image_user_uid"] == 1000
    assert calls == [("/usr/bin/setfacl", "-m", "u:1000:r--", str(realm))]
    assert other_secret.stat().st_mode == other_mode_before
    assert "unrelated-secret" not in str(result)


def test_realm_acl_rejects_root_or_unresolved_image_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    realm = tmp_path / "realm.json"
    realm.write_text("synthetic", encoding="utf-8")
    monkeypatch.setattr(prepare_acceptance, "_supports_posix_acl", lambda: True)
    monkeypatch.setattr(
        prepare_acceptance.shutil, "which", lambda *_args: "/usr/bin/setfacl"
    )
    for image_user in ("0", "keycloak", ""):

        def image_info(
            *args: str, timeout: int = 15, user: str = image_user
        ) -> subprocess.CompletedProcess[str]:
            assert timeout == 15
            return subprocess.CompletedProcess(
                args, 0, "sha256:" + "a" * 64 + "|" + user, ""
            )

        monkeypatch.setattr(
            prepare_acceptance,
            "_quiet_command",
            image_info,
        )
        with pytest.raises(prepare_acceptance.AcceptancePreflightError):
            prepare_acceptance.grant_keycloak_realm_read(
                "quay.io/keycloak/keycloak:26.0", realm
            )
