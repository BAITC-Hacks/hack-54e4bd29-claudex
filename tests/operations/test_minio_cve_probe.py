"""IAM import regression never publishes temporary credentials or archive data."""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from scripts.operations import minio_cve_probe

PROJECT = "phase8-iam-test123"


def test_escalation_archive_uses_synthetic_mapping(tmp_path: Path) -> None:
    original = tmp_path / "original.zip"
    with zipfile.ZipFile(original, "w") as archive:
        archive.writestr("iam-assets/user_mappings.json", "{}")
    output = tmp_path / "escalation.zip"
    minio_cve_probe._escalation_archive(original, output, "synthetic-limited")
    with zipfile.ZipFile(output) as archive:
        mapped = json.loads(archive.read("iam-assets/user_mappings.json"))
    assert mapped["synthetic-limited"]["policy"] == "consoleAdmin"


def test_denial_requires_access_denied_not_just_failure() -> None:
    assert minio_cve_probe._denied(
        subprocess.CompletedProcess([], 1, "", "Access Denied")
    )
    assert not minio_cve_probe._denied(
        subprocess.CompletedProcess([], 1, "", "network down")
    )
    assert not minio_cve_probe._denied(subprocess.CompletedProcess([], 0, "", ""))


def test_prestart_scan_gate_prevents_any_docker_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / PROJECT / "security"
    path.mkdir(parents=True)
    (path / "scan-summary.json").write_text(
        json.dumps({"functional_acceptance_allowed": False, "images": {}})
    )
    (path.parent / "advisory-gate.json").write_text(
        json.dumps({"synthetic_functional_review": "PASS"})
    )
    monkeypatch.setattr(minio_cve_probe, "BUILD_ROOT", tmp_path)
    monkeypatch.setattr(
        minio_cve_probe,
        "_command",
        lambda *_a, **_kw: pytest.fail("Docker was touched before scan gate"),
    )
    with pytest.raises(ValueError, match="security gate"):
        minio_cve_probe.verify(PROJECT)


def test_probe_cleans_resources_and_does_not_persist_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / PROJECT / "security"
    path.mkdir(parents=True)
    (path / "scan-summary.json").write_text(
        json.dumps(
            {
                "functional_acceptance_allowed": True,
                "images": {"server": {"critical": 0}, "client": {"critical": 0}},
            }
        )
    )
    (path.parent / "advisory-gate.json").write_text(
        json.dumps({"synthetic_functional_review": "PASS"})
    )
    monkeypatch.setattr(minio_cve_probe, "BUILD_ROOT", tmp_path)
    monkeypatch.setattr(
        minio_cve_probe,
        "load_built_images",
        lambda _p: {"server": "sha256:" + "1" * 64, "client": "sha256:" + "2" * 64},
    )
    monkeypatch.setattr(minio_cve_probe.secrets, "token_hex", lambda _n: "fake-secret")
    commands: list[tuple[str, ...]] = []

    def fake_command(*args: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(list(args), 0, "", "")

    def fake_mc(
        _image: str, _network: str, _env_file: Path, work: Path, *args: str
    ) -> subprocess.CompletedProcess[str]:
        if "export" in args:
            with zipfile.ZipFile(work / "admin-iam-info.zip", "w") as archive:
                archive.writestr("iam-assets/user_mappings.json", "{}")
        if "import" in args and args[-2] in ("limited", "service"):
            return subprocess.CompletedProcess(list(args), 1, "", "Access Denied")
        return subprocess.CompletedProcess(list(args), 0, "", "")

    monkeypatch.setattr(minio_cve_probe, "_command", fake_command)
    monkeypatch.setattr(minio_cve_probe, "_mc", fake_mc)
    result = minio_cve_probe.verify(PROJECT)
    assert result["limited_user_import"] == "DENIED"
    assert result["service_account_import"] == "DENIED"
    assert result["admin_import"] == "ALLOWED"
    network_create = next(row for row in commands if row[:2] == ("network", "create"))
    assert "--internal" in network_create
    assert all("--publish" not in row and "--privileged" not in row for row in commands)
    assert [row[0] for row in commands[-3:]] == ["rm", "volume", "network"]
    assert not list((tmp_path / PROJECT).glob("*-iam-*"))
    assert (
        "fake-secret" not in (tmp_path / PROJECT / "iam-probe-summary.json").read_text()
    )
