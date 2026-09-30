"""Publish the local synthetic profile into one fresh READY acceptance project."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from scripts.local_demo.dataset import DATASETS, DELIVERY_IDS, generate
from scripts.operations.prepare_acceptance import (
    ARTIFACTS,
    ROOT,
    _compose_command,
    validate_project_name,
)


def _run(*command: str) -> None:
    try:
        result = subprocess.run(  # noqa: S603 — fixed argv for one validated project
            list(command),
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "Local demo bootstrap command unavailable or timed out"
        ) from exc
    if result.returncode:
        # Docker output can contain connection details; retain only the exit code.
        raise RuntimeError(f"Local demo bootstrap step failed (exit {result.returncode})")


def command_plan(project: str, output: Path) -> tuple[tuple[str, ...], ...]:
    """Build fixed commands, all scoped to one acceptance project."""
    validate_project_name(project)
    compose = tuple(_compose_command(project, output))
    commands = [(
        *compose, "exec", "-T", "-e", "LOCAL_SYNTHETIC_DEMO=1", "backend",
        "python", "-m", "seeds.local_demo_preflight", *DELIVERY_IDS,
    ), (
        *compose, "exec", "-T", "-e", "LOCAL_SYNTHETIC_DEMO=1", "backend",
        "python", "-m", "seeds.local_demo_seed",
    )]
    for dataset in DATASETS:
        manifest = f"/data/source/manifest-{dataset}.json"
        commands.append((
            *compose, "run", "--rm", "pipeline", "approve-manifest",
            "--manifest", manifest, "--actor", "local-demo-owner",
            "--evidence-ref", "local-demo-profile-v1",
        ))
        commands.append((
            *compose, "run", "--rm", "pipeline", "import",
            "--dataset", dataset, "--manifest", manifest,
        ))
    commands.append((
        *compose, "exec", "-T", "-e", "LOCAL_SYNTHETIC_DEMO=1", "backend",
        "python", "-m", "seeds.local_demo_mappings",
    ))
    return tuple(commands)


def _is_local_env(path: Path) -> bool:
    return any(
        line.strip() == "APP_ENV=local"
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def bootstrap(project: str) -> dict[str, int]:
    """Seed/import only after checking the exact fresh project and empty source."""
    validate_project_name(project)
    if not project.startswith("phase8-local-demo-"):
        raise ValueError("Local demo requires its own phase8-local-demo- project")
    output = ARTIFACTS / project
    if not (output / ".env").is_file() or not (output / "realm.json").is_file():
        raise ValueError("Project must be prepared as an isolated acceptance environment")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("project") != project or manifest.get("dataset") != "synthetic-only":
        raise ValueError("Acceptance manifest does not match the local synthetic project")
    if manifest.get("status") != "READY":
        raise ValueError("Acceptance project must be READY before bootstrap")
    if not _is_local_env(output / ".env"):
        raise ValueError("Local demo requires APP_ENV=local")
    source = output / "source-empty"
    if not source.is_dir() or any(source.iterdir()):
        raise ValueError("Local demo source directory must be empty")

    commands = command_plan(project, output)
    _run(*commands[0])
    counts = generate(source)
    for command in commands[1:]:
        _run(*command)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    counts = bootstrap(args.project)
    print("Published local synthetic records: " + ", ".join(
        f"{dataset}={counts[dataset]}" for dataset in DATASETS
    ))


if __name__ == "__main__":
    main()
