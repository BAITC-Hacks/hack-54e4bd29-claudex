"""Verify real 503 handling by stopping only a namespaced disposable ClickHouse.

Always restarts the dependency, including after a failed Playwright assertion.
Neither Compose volumes nor medical source files are modified.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess

from scripts.operations.prepare_acceptance import (
    ARTIFACTS,
    ROOT,
    _compose_command,
    _run,
    _wait_http,
    validate_project_name,
)


def run(project: str) -> None:
    """Stop ClickHouse, run one browser failure test, then restore readiness."""
    validate_project_name(project)
    output = ARTIFACTS / project
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    origin = manifest["origin"]
    if manifest["project"] != project or not origin.startswith("http://127.0.0.1:"):
        raise ValueError("Only loopback isolated phase8 projects are supported")
    if manifest["status"] != "READY":
        raise ValueError("Isolated project must be ready before failure test")
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm executable unavailable")
    compose = _compose_command(project, output)
    browser_result: subprocess.CompletedProcess[str] | None = None
    _run(*compose, "stop", "clickhouse")
    try:
        env = {
            **os.environ,
            "MEDSIGNAL_E2E_BASE_URL": origin,
            "MEDSIGNAL_E2E_REALM": str(output / "realm.json"),
            "MEDSIGNAL_E2E_DEGRADED": "1",
        }
        browser_result = subprocess.run(  # noqa: S603 — npm binary resolved from PATH
            [
                npm,
                "run",
                "test:e2e",
                "--",
                "--grep",
                "dependency outage",
                "--timeout",
                "60000",
            ],
            cwd=ROOT / "frontend",
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
    finally:
        _run(*compose, "start", "clickhouse")
        _wait_http(origin + "/api/v1/ready", deadline_seconds=120)
    if browser_result is None or browser_result.returncode:
        # Playwright failure logs can contain a callback URL; keep them local.
        raise RuntimeError("Degraded browser test failed; ClickHouse was restored")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    run(args.project)
    print("HTTP 503 and dashboard unavailability: PASS; ClickHouse restored")


if __name__ == "__main__":
    main()
