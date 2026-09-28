"""Load only generated synthetic fixtures into a fresh phase8 acceptance project.

The host source directory is checked empty before generation. Docker mounts it
read-only in the pipeline container. No medical dataset path is accepted.
"""

from __future__ import annotations

import argparse
import subprocess

from scripts.acceptance.synthetic_dataset import COUNTS, generate
from scripts.operations.prepare_acceptance import (
    ARTIFACTS,
    ROOT,
    _compose_command,
    validate_project_name,
)

PUBLISHABLE = ("REFERRALS", "WAITING", "REFUSALS")


def _run(*command: str, input_text: str | None = None) -> None:
    result = subprocess.run(  # noqa: S603 — fixed argv from validated project
        list(command),
        cwd=ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        # Docker and application stderr may contain connection details; do not echo it.
        raise RuntimeError(f"Synthetic bootstrap step failed: {command[-1]}")


def bootstrap(project: str) -> dict[str, int]:
    """Generate fixtures, approve manifests, import and publish three datasets."""
    validate_project_name(project)
    output = ARTIFACTS / project
    if not (output / ".env").is_file() or not (output / "realm.json").is_file():
        raise ValueError("Project must be prepared as an isolated phase8 environment")
    source = output / "source-empty"
    if not source.is_dir() or any(source.iterdir()):
        raise ValueError("Synthetic source directory must be empty")
    compose = _compose_command(project, output)
    counts = generate(source)
    if counts != COUNTS:
        raise RuntimeError("Synthetic fixture generation changed unexpectedly")

    _run(*compose, "exec", "-T", "backend", "python", "-m", "seeds.dev_seed")
    for dataset in PUBLISHABLE:
        manifest = f"/data/source/manifest-{dataset}.json"
        _run(
            *compose,
            "run",
            "--rm",
            "pipeline",
            "approve-manifest",
            "--manifest",
            manifest,
            "--actor",
            "phase8-synthetic-owner",
            "--evidence-ref",
            "phase8-synthetic-fixture-v1",
        )
        _run(
            *compose,
            "run",
            "--rm",
            "pipeline",
            "import",
            "--dataset",
            dataset,
            "--manifest",
            manifest,
        )
    mapping_path = ROOT / "scripts/acceptance/publish_synthetic_mappings.py"
    mapping_script = mapping_path.read_text(encoding="utf-8")
    _run(
        *compose,
        "exec",
        "-T",
        "-e",
        "PHASE8_SYNTHETIC_ACCEPTANCE=1",
        "backend",
        "python",
        "-",
        input_text=mapping_script,
    )
    return {dataset: counts[dataset] for dataset in PUBLISHABLE}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    counts = bootstrap(args.project)
    print(
        "Published synthetic records: "
        + ", ".join(f"{dataset}={count}" for dataset, count in counts.items())
    )
    print("TREATED was deliberately not published: reporting period unconfirmed")


if __name__ == "__main__":
    main()
