from __future__ import annotations

import argparse
import json
import shutil
import subprocess

from scripts.operations.common import require_phase8_namespace


def reset_command(project: str) -> list[str]:
    project = require_phase8_namespace(project)
    return [
        "docker",
        "compose",
        "-p",
        project,
        "down",
        "--volumes",
        "--remove-orphans",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove only an isolated phase8-* Compose project"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    command = reset_command(args.project)
    if not args.execute:
        print(json.dumps({"status": "DRY_RUN", "project": args.project}))
        return 0
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker executable not found")
    command[0] = docker
    subprocess.run(command, check=True)  # noqa: S603 -- argv validated above
    print(json.dumps({"status": "RESET", "project": args.project}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
