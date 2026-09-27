"""Guard the browser job against optional tests and unsafe artifacts."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_browser_acceptance_is_required_and_uses_namespaced_cleanup() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["browser-acceptance"]
    steps = job["steps"]
    commands = "\n".join(str(step.get("run", "")) for step in steps)
    assert job["env"]["ACCEPTANCE_PROJECT"].startswith("phase8-")
    assert all(step.get("continue-on-error") is not True for step in steps)
    assert "bootstrap_synthetic" in commands
    assert "npm --prefix frontend run test:e2e" in commands
    assert "run_degraded_browser" in commands
    assert '--project-name "$ACCEPTANCE_PROJECT"' in commands
    assert "down --volumes" in commands


def test_browser_artifact_contains_only_numeric_summaries() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["browser-acceptance"]["steps"]
    artifact = next(
        step
        for step in steps
        if step.get("with", {}).get("name") == "synthetic-browser-counts"
    )
    paths = set(artifact["with"]["path"].splitlines())
    assert paths == {
        "tmp/playwright-summary.json",
        "tmp/playwright-degraded-summary.json",
    }


def test_browser_failure_artifact_contains_only_sanitized_diagnostics() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["browser-acceptance"]["steps"]
    artifact = next(
        step
        for step in steps
        if step.get("with", {}).get("name") == "acceptance-start-diagnostics"
    )
    path = artifact["with"]["path"]
    assert path.endswith("/sanitized-diagnostics.json")
    assert "private-diagnostics" not in path
    assert artifact.get("if") == "always()"


def test_minio_evidence_upload_excludes_credentials_and_iam_archives() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    artifact = next(
        step
        for step in workflow["jobs"]["browser-acceptance"]["steps"]
        if step.get("with", {}).get("name") == "minio-source-build-evidence"
    )
    paths = artifact["with"]["path"]
    assert "iam-probe-summary.json" in paths
    assert "advisory-gate.json" in paths
    assert ".env" not in paths
    assert ".zip" not in paths
    assert "*.json" not in paths


def test_browser_builds_and_scans_source_images_before_normal_start() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["browser-acceptance"]["steps"]
    commands = [str(step.get("run", "")) for step in steps]
    build = next(
        i for i, command in enumerate(commands) if "minio_source_build" in command
    )
    scan = next(i for i, command in enumerate(commands) if "minio_source_scan" in command)
    advisory = next(
        i for i, command in enumerate(commands) if "minio_advisory_gate" in command
    )
    iam_probe = next(
        i for i, command in enumerate(commands) if "minio_cve_probe" in command
    )
    prepare = next(
        i for i, command in enumerate(commands) if "prepare_acceptance prepare" in command
    )
    runtime = next(
        i for i, command in enumerate(commands) if "verify_minio_source" in command
    )
    fixtures = next(
        i for i, command in enumerate(commands) if "bootstrap_synthetic" in command
    )
    assert build < advisory < scan < iam_probe < prepare < runtime < fixtures
    assert "--patched-acceptance" in commands[build]
    assert "--minio-source-build" in commands[prepare]
    assert not any("probe_public_images" in command for command in commands)
    assert all(step.get("continue-on-error") is not True for step in steps)
