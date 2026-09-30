"""The local demo bootstrap addresses only one fresh READY phase8 project."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT = "phase8-local-demo-test1"


def _prepared(tmp_path: Path, *, status: str = "READY") -> Path:
    output = tmp_path / PROJECT
    output.mkdir()
    (output / "source-empty").mkdir()
    (output / ".env").write_text("APP_ENV=local\n", encoding="utf-8")
    (output / "realm.json").write_text("{}\n", encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps({"project": PROJECT, "dataset": "synthetic-only", "status": status}),
        encoding="utf-8",
    )
    return output


def test_bootstrap_refuses_dirty_source_without_touching_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.local_demo import bootstrap as module

    output = _prepared(tmp_path)
    existing = output / "source-empty" / "existing.csv"
    existing.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(module, "ARTIFACTS", tmp_path)
    with pytest.raises(ValueError, match="empty"):
        module.bootstrap(PROJECT)
    assert existing.read_text(encoding="utf-8") == "keep"


def test_bootstrap_refuses_unready_project_before_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.local_demo import bootstrap as module

    output = _prepared(tmp_path, status="PREPARED")
    monkeypatch.setattr(module, "ARTIFACTS", tmp_path)
    with pytest.raises(ValueError, match="READY"):
        module.bootstrap(PROJECT)
    assert list((output / "source-empty").iterdir()) == []


def test_command_plan_never_addresses_another_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.local_demo import bootstrap as module

    monkeypatch.setattr(
        module,
        "_compose_command",
        lambda project, _output: ["docker", "compose", "--project-name", project],
    )
    commands = module.command_plan(PROJECT, tmp_path / PROJECT)
    assert len(commands) == 9
    assert all("phase8-local-main-20260929a" not in argv for argv in commands)
    assert all(argv[2:4] == ("--project-name", PROJECT) for argv in commands)
    assert "seeds.local_demo_preflight" in commands[0]
    assert sum("approve-manifest" in argv for argv in commands) == 3
    assert sum("import" in argv for argv in commands) == 3


def test_bootstrap_publishes_only_generated_manifest_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.local_demo import bootstrap as module

    output = _prepared(tmp_path)
    monkeypatch.setattr(module, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        module,
        "_compose_command",
        lambda project, _output: ["docker", "compose", "--project-name", project],
    )
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(module, "_run", lambda *argv: calls.append(argv))
    counts = module.bootstrap(PROJECT)
    assert counts["WAITING"] == 60
    assert counts["REFUSALS"] == 156
    assert counts["REFERRALS"] > 1800
    assert len(calls) == 9
    assert "seeds.local_demo_preflight" in calls[0]
    assert all(PROJECT in argv for argv in calls)
    for dataset, count in counts.items():
        manifest = json.loads(
            (output / "source-empty" / f"manifest-{dataset}.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["expected_rows"] == count


def test_bootstrap_checks_delivery_reuse_before_generating_or_seeding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.local_demo import bootstrap as module

    output = _prepared(tmp_path)
    monkeypatch.setattr(module, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        module,
        "_compose_command",
        lambda project, _output: ["docker", "compose", "--project-name", project],
    )
    calls: list[tuple[str, ...]] = []

    def reject_reused_delivery(*argv: str) -> None:
        calls.append(argv)
        raise RuntimeError("Existing local demo delivery ID")

    monkeypatch.setattr(module, "_run", reject_reused_delivery)
    with pytest.raises(RuntimeError, match="Existing local demo delivery ID"):
        module.bootstrap(PROJECT)

    assert len(calls) == 1
    assert "seeds.local_demo_preflight" in calls[0]
    assert list((output / "source-empty").iterdir()) == []
