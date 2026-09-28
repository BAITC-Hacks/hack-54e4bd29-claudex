"""Guard the acceptance loader against real sources or broad imports."""

import sys
from pathlib import Path

import pytest

from scripts.acceptance import bootstrap_synthetic


def _prepared(tmp_path: Path, project: str) -> Path:
    output = tmp_path / project
    output.mkdir()
    (output / ".env").write_text("test-only\n", encoding="utf-8")
    (output / "realm.json").write_text("{}\n", encoding="utf-8")
    (output / "source-empty").mkdir()
    return output


def test_bootstrap_rejects_nonempty_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = "phase8-accept-test1234"
    output = _prepared(tmp_path, project)
    (output / "source-empty" / "unrelated.csv").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap_synthetic, "ARTIFACTS", tmp_path)
    with pytest.raises(ValueError, match="must be empty"):
        bootstrap_synthetic.bootstrap(project)


def test_bootstrap_imports_only_three_published_synthetic_datasets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = "phase8-accept-test1234"
    _prepared(tmp_path, project)
    monkeypatch.setattr(bootstrap_synthetic, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        bootstrap_synthetic,
        "_compose_command",
        lambda project, _output: ["docker", "compose", "-p", project],
    )
    calls: list[tuple[str, ...]] = []

    def record(*args: str, input_text: str | None = None) -> None:
        calls.append(args)
        if input_text is not None:
            assert "SPECS" in input_text

    monkeypatch.setattr(bootstrap_synthetic, "_run", record)

    counts = bootstrap_synthetic.bootstrap(project)

    assert counts == {"REFERRALS": 30, "WAITING": 22, "REFUSALS": 24}
    imports = [call for call in calls if "import" in call]
    assert len(imports) == 3
    assert {call[call.index("--dataset") + 1] for call in imports} == set(counts)
    assert all("TREATED" not in call for call in calls)
    assert any("PHASE8_SYNTHETIC_ACCEPTANCE=1" in call for call in calls)


def test_bootstrap_requires_phase8_namespace(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="phase8-"):
        bootstrap_synthetic.bootstrap("medsignal")


def test_bootstrap_decodes_utf8_subprocess_output_on_windows() -> None:
    bootstrap_synthetic._run(
        sys.executable,
        "-c",
        "import sys; sys.stdout.buffer.write('синтетические'.encode('utf-8'))",
    )
