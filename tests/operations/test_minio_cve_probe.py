"""IAM import regression never publishes temporary credentials or archive data."""

from __future__ import annotations

import json
import subprocess
import sys
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


def test_denial_requires_structured_server_code_not_local_text() -> None:
    assert minio_cve_probe._denied(
        subprocess.CompletedProcess(
            [],
            1,
            json.dumps(
                {
                    "status": "error",
                    "error": {
                        "type": "fatal",
                        "cause": {"error": {"Code": "AccessDenied"}},
                    },
                }
            ),
            "",
        )
    )
    assert not minio_cve_probe._denied(
        subprocess.CompletedProcess([], 1, "", "permission denied opening local ZIP")
    )
    assert not minio_cve_probe._denied(
        subprocess.CompletedProcess(
            [],
            1,
            json.dumps(
                {
                    "status": "error",
                    "error": {"cause": {"error": {"Code": "InvalidAccessKeyId"}}},
                }
            ),
            "",
        )
    )
    assert not minio_cve_probe._denied(
        subprocess.CompletedProcess(
            [],
            1,
            '{"status":"error","error":{"type":"fatal","cause":{"error":{"Code":"InvalidAccessKeyId"}}}}',
            "",
        )
    )
    assert not minio_cve_probe._denied(
        subprocess.CompletedProcess([], 1, '{"status":"error","error":', "")
    )
    assert not minio_cve_probe._denied(subprocess.CompletedProcess([], 0, "", ""))


def test_admin_import_requires_structured_result_without_failed_entities() -> None:
    assert minio_cve_probe._admin_import_valid(
        subprocess.CompletedProcess([], 0, '{"added":{},"failed":{}}', "")
    )
    assert not minio_cve_probe._admin_import_valid(
        subprocess.CompletedProcess([], 0, '{"failed":{"users":[{"name":"x"}]}}', "")
    )
    assert not minio_cve_probe._admin_import_valid(
        subprocess.CompletedProcess([], 0, "not json", "")
    )


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
    summary = json.loads((path.parent / "iam-probe-summary.json").read_text())
    assert summary["verdict"] == "ERROR"
    assert summary["failed_stage"] == "prerequisites"
    assert summary["assertions"] == {
        "limited_import": "NOT_RUN",
        "service_import": "NOT_RUN",
        "admin_import": "NOT_RUN",
    }


def test_command_failure_records_stage_and_exit_code_without_stderr(
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
        lambda _: {"server": "sha256:" + "1" * 64, "client": "sha256:" + "2" * 64},
    )
    fake_secret = "fake-private-credential-123"  # noqa: S105 — leak canary

    def failed_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 17, "", fake_secret + " permission denied")

    monkeypatch.setattr(minio_cve_probe.subprocess, "run", failed_run)
    with pytest.raises(RuntimeError):
        minio_cve_probe.verify(PROJECT)
    content = (path.parent / "iam-probe-summary.json").read_text()
    summary = json.loads(content)
    assert summary["failed_stage"] == "create_network"
    assert summary["command_exit_code"] == 17
    assert summary["primary_error"]["category"] == "DOCKER_COMMAND_FAILED"
    assert summary["assertions"]["limited_import"] == "NOT_RUN"
    assert fake_secret not in content


def test_cleanup_failure_does_not_hide_primary_error_and_other_cleanup_runs(
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
        lambda _: {
            "server": "sha256:" + "1" * 64,
            "client": "sha256:" + "2" * 64,
        },
    )
    calls: list[tuple[str, ...]] = []

    def fake_command(*args: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:2] == ("run", "--detach"):
            raise RuntimeError("controlled setup failure")
        if args[:2] == ("volume", "rm"):
            return subprocess.CompletedProcess([], 2, "", "canary-secret")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(minio_cve_probe, "_command", fake_command)
    with pytest.raises(RuntimeError, match="controlled setup failure"):
        minio_cve_probe.verify(PROJECT)
    result = json.loads((path.parent / "iam-probe-summary.json").read_text())
    assert result["failed_stage"] == "start_server"
    assert result["primary_error"]["category"] == "PROBE_STAGE_ERROR"
    assert result["cleanup_errors"] == ["VOLUME_REMOVE_FAILED"]
    assert [item[:2] for item in calls[-2:]] == [("volume", "rm"), ("network", "rm")]
    assert "canary-secret" not in json.dumps(result)


def test_timed_out_create_removes_only_probe_owned_partial_resource(
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
        lambda _: {
            "server": "sha256:" + "1" * 64,
            "client": "sha256:" + "2" * 64,
        },
    )
    calls: list[tuple[str, ...]] = []
    owner: str | None = None

    def fake_command(*args: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal owner
        calls.append(args)
        if args[:2] == ("network", "create"):
            owner = next(
                x.split("=", 1)[1]
                for x in args
                if x.startswith("org.medsignal.acceptance.probe=")
            )
            raise subprocess.TimeoutExpired(["docker", "network", "create"], 90)
        if args[:2] == ("network", "inspect"):
            return subprocess.CompletedProcess([], 0, owner or "", "")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(minio_cve_probe, "_command", fake_command)
    with pytest.raises(subprocess.TimeoutExpired):
        minio_cve_probe.verify(PROJECT)
    assert ("network", "rm", f"{PROJECT}-iam-probe-net") in calls
    result = json.loads((path.parent / "iam-probe-summary.json").read_text())
    assert result["failed_stage"] == "create_network"
    assert result["primary_error"]["category"] == "TIMEOUT"
    assert result["cleanup_status"] == "PASS"


def test_mc_setup_failure_retains_exit_code_and_safe_stage(
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
        lambda _: {
            "server": "sha256:" + "1" * 64,
            "client": "sha256:" + "2" * 64,
        },
    )
    monkeypatch.setattr(
        minio_cve_probe,
        "_command",
        lambda *_a, **_kw: subprocess.CompletedProcess([], 0, "", ""),
    )

    def fake_mc(
        _image: str, _network: str, _env: Path, _work: Path, *args: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            [], 7 if args[:3] == ("admin", "user", "add") else 0, "", "private-value"
        )

    monkeypatch.setattr(minio_cve_probe, "_mc", fake_mc)
    with pytest.raises(RuntimeError):
        minio_cve_probe.verify(PROJECT)
    content = (path.parent / "iam-probe-summary.json").read_text()
    summary = json.loads(content)
    assert summary["failed_stage"] == "create_limited_user"
    assert summary["command_exit_code"] == 7
    assert summary["primary_error"] == {
        "category": "MC_COMMAND_FAILED",
        "message": "Disposable limited user creation failed",
    }
    assert "private-value" not in content


def test_cli_reports_safe_failure_stage_without_raw_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / PROJECT
    source.mkdir()
    (source / "iam-probe-summary.json").write_text(
        json.dumps(
            {
                "verdict": "ERROR",
                "failed_stage": "create_limited_user",
                "command_exit_code": 7,
                "primary_error": {"category": "MC_COMMAND_FAILED"},
            }
        )
    )
    monkeypatch.setattr(minio_cve_probe, "BUILD_ROOT", tmp_path)
    monkeypatch.setattr(
        minio_cve_probe,
        "verify",
        lambda _project: (_ for _ in ()).throw(RuntimeError("private-value")),
    )
    monkeypatch.setattr(sys, "argv", ["iam-probe", "--project", PROJECT])
    assert minio_cve_probe.main() == 2
    output = capsys.readouterr().err
    assert "create_limited_user" in output
    assert "MC_COMMAND_FAILED" in output
    assert "private-value" not in output


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
        if args[-4:-2] == ("user", "info") or "info" in args:
            return subprocess.CompletedProcess(
                list(args), 0, '{"policyName":"readwrite"}', ""
            )
        if "import" in args and args[-2] in ("limited", "service"):
            return subprocess.CompletedProcess(
                list(args),
                1,
                json.dumps(
                    {
                        "status": "error",
                        "error": {
                            "type": "fatal",
                            "cause": {"error": {"Code": "AccessDenied"}},
                        },
                    }
                ),
                "",
            )
        if "import" in args:
            return subprocess.CompletedProcess(
                list(args), 0, '{"added":{},"failed":{}}', ""
            )
        return subprocess.CompletedProcess(list(args), 0, "", "")

    monkeypatch.setattr(minio_cve_probe, "_command", fake_command)
    monkeypatch.setattr(minio_cve_probe, "_mc", fake_mc)
    result = minio_cve_probe.verify(PROJECT)
    assert result["limited_user_import"] == "DENIED"
    assert result["service_account_import"] == "DENIED"
    assert result["admin_import"] == "ALLOWED"
    assert result["assertions"] == {
        "limited_import": "PASS",
        "service_import": "PASS",
        "admin_import": "PASS",
    }
    assert result["permission_unchanged"] is True
    assert result["stage_durations_seconds"]["create_network"] >= 0
    assert result["stage_durations_seconds"]["admin_positive_control"] >= 0
    network_create = next(row for row in commands if row[:2] == ("network", "create"))
    assert "--internal" in network_create
    assert all("--publish" not in row and "--privileged" not in row for row in commands)
    assert [row[0] for row in commands[-3:]] == ["rm", "volume", "network"]
    assert not list((tmp_path / PROJECT).glob("*-iam-*"))
    assert (
        "fake-secret" not in (tmp_path / PROJECT / "iam-probe-summary.json").read_text()
    )
