"""Source-build runtime checks stay inside the disposable acceptance project."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.operations import verify_minio_source


def test_runtime_probe_refuses_default_or_non_namespaced_project(tmp_path: Path) -> None:
    project = "phase8-accept-abcd1234"
    folder = tmp_path / project
    folder.mkdir()
    (folder / "manifest.json").write_text(
        json.dumps({"minio_mode": "DEFAULT"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="source mode"):
        verify_minio_source.verify(project, acceptance_root=tmp_path)
    with pytest.raises(ValueError, match="phase8-"):
        verify_minio_source.verify("medsignal", acceptance_root=tmp_path)


def test_runtime_probe_uses_all_four_scoped_identities_and_reruns_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = "phase8-accept-abcd1234"
    folder = tmp_path / project
    folder.mkdir()
    (folder / "manifest.json").write_text(
        json.dumps({"minio_mode": "PROJECT_BUILT_SOURCE"}), encoding="utf-8"
    )
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        verify_minio_source,
        "load_built_images",
        lambda _: {"server": "sha256:" + "1" * 64, "client": "sha256:" + "2" * 64},
    )
    monkeypatch.setattr(
        verify_minio_source, "_compose_command", lambda *_: ["docker", "compose"]
    )

    def fake_run(*command: str) -> str:
        calls.append(command)
        if command[-3:] == ("ps", "--all", "--format"):
            return ""
        if "ps" in command:
            return "\n".join(
                json.dumps(row)
                for row in (
                    {"Service": "minio", "State": "running", "Health": "healthy"},
                    {"Service": "minio-init", "State": "exited", "ExitCode": 0},
                )
            )
        return ""

    monkeypatch.setattr(verify_minio_source, "_run", fake_run)
    result = verify_minio_source.verify(project, acceptance_root=tmp_path)
    assert result["bootstrap_repeated"] is True
    assert set(result["identities_checked"]) == {"app", "worker", "pipeline", "mlflow"}
    assert any("minio-init" in call and "run" in call for call in calls)
    assert any("backend" in call and "exec" in call for call in calls)
    assert any("worker" in call and "exec" in call for call in calls)
    assert any("pipeline" in call and "run" in call for call in calls)
    assert any("mlflow" in call and "exec" in call for call in calls)
    assert all("MINIO_ROOT_PASSWORD" not in " ".join(call) for call in calls)


def test_runtime_probe_rejects_missing_compose_service_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = "phase8-accept-abcd1234"
    folder = tmp_path / project
    folder.mkdir()
    (folder / "manifest.json").write_text(
        json.dumps({"minio_mode": "PROJECT_BUILT_SOURCE"}), encoding="utf-8"
    )
    monkeypatch.setattr(verify_minio_source, "load_built_images", lambda _: {})
    monkeypatch.setattr(
        verify_minio_source, "_compose_command", lambda *_: ["docker", "compose"]
    )
    monkeypatch.setattr(verify_minio_source, "_run", lambda *_: "")
    with pytest.raises(RuntimeError, match="health"):
        verify_minio_source.verify(project, acceptance_root=tmp_path)
