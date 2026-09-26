"""Disposable failure test must always restore its dependency."""

import json
import subprocess
from pathlib import Path

import pytest

from scripts.acceptance import run_degraded_browser


@pytest.mark.parametrize("browser_exit", [0, 1])
def test_degraded_browser_restores_clickhouse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, browser_exit: int
) -> None:
    project = "phase8-accept-test1234"
    output = tmp_path / project
    output.mkdir()
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "project": project,
                "origin": "http://127.0.0.1:55123",
                "status": "READY",
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []
    monkeypatch.setattr(run_degraded_browser, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(
        run_degraded_browser,
        "_compose_command",
        lambda _project, _output: ["docker", "compose"],
    )
    monkeypatch.setattr(run_degraded_browser.shutil, "which", lambda _name: "npm")
    monkeypatch.setattr(
        run_degraded_browser,
        "_run",
        lambda *args: calls.append(args[-2]),
    )

    def fake_wait(url: str, *, deadline_seconds: int) -> None:
        assert deadline_seconds == 120
        calls.append(f"ready:{url}")

    monkeypatch.setattr(run_degraded_browser, "_wait_http", fake_wait)

    def fake_browser(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append("browser")
        return subprocess.CompletedProcess([], browser_exit)

    monkeypatch.setattr(run_degraded_browser.subprocess, "run", fake_browser)

    if browser_exit:
        with pytest.raises(RuntimeError, match="restored"):
            run_degraded_browser.run(project)
    else:
        run_degraded_browser.run(project)
    assert calls == [
        "stop",
        "browser",
        "start",
        "ready:http://127.0.0.1:55123/api/v1/ready",
    ]
