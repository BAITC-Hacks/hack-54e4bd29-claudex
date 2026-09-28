from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scripts.security.scan_secrets import candidate_paths, scan_paths


def test_secret_scanner_reports_rule_and_path_but_not_value(tmp_path: Path) -> None:
    # Split so repository scanners do not mistake the detector fixture itself
    # for a committed credential; scan_paths still receives the joined value.
    secret = "sk-proj-" + "1234567890abcdefghijklmnopqrstuv"
    target = tmp_path / "leak.txt"
    target.write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")

    findings = scan_paths([target])

    assert findings == [{"path": str(target), "line": 1, "rule": "openai-key"}]
    assert secret not in repr(findings)


def test_local_dev_markers_are_not_production_secret_findings(tmp_path: Path) -> None:
    target = tmp_path / "realm.json"
    target.write_text('"password": "synthetic-local_dev_only"\n', encoding="utf-8")
    assert scan_paths([target]) == []


def test_candidate_paths_include_tracked_and_untracked_non_ignored_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked = tmp_path / "tracked.py"
    untracked = tmp_path / "new.py"
    tracked.write_text("tracked", encoding="utf-8")
    untracked.write_text("untracked", encoding="utf-8")

    monkeypatch.setattr("scripts.security.scan_secrets.shutil.which", lambda _: "git")
    monkeypatch.setattr(
        "scripts.security.scan_secrets.subprocess.run",
        lambda *args, **_kwargs: CompletedProcess(
            args=args[0], returncode=0, stdout=b"tracked.py\0new.py\0"
        ),
    )

    assert candidate_paths(tmp_path) == [tracked, untracked]
