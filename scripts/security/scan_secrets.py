"""Conservative secret scanner that never emits matched values."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import TypedDict


class Finding(TypedDict):
    path: str
    line: int
    rule: str


RULES = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai-key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"),
    "anthropic-key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{24,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
}

DISALLOWED_TRACKED = re.compile(
    r"(^|/)(\.env|settings\.local\.json|node_modules|\.next|__pycache__)(/|$)"
    r"|\.(pem|key|p12|pfx)$",
    re.IGNORECASE,
)


def scan_paths(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(lines, start=1):
            if "local_dev_only" in line:
                continue
            for rule, pattern in RULES.items():
                if pattern.search(line):
                    findings.append({"path": str(path), "line": number, "rule": rule})
    return findings


def candidate_paths(root: Path) -> list[Path]:
    """Return every tracked or untracked, non-ignored release candidate file."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable not found")
    result = subprocess.run(  # noqa: S603 -- static git argv, no shell
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    relative = [item for item in result.stdout.decode().split("\0") if item]
    disallowed = [item for item in relative if DISALLOWED_TRACKED.search(item)]
    if disallowed:
        raise ValueError("disallowed tracked paths: " + ", ".join(disallowed))
    return [root / item for item in relative]


def scan_history(root: Path) -> list[Finding]:
    """Scan patch history without retaining or returning matched text."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable not found")
    result = subprocess.run(  # noqa: S603 -- static git argv, no shell
        [git, "log", "--all", "-p", "--no-ext-diff", "--unified=0"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    findings: list[Finding] = []
    current = "git-history"
    for number, line in enumerate(
        result.stdout.decode("utf-8", errors="replace").splitlines(), start=1
    ):
        if line.startswith("+++ b/"):
            current = line[6:]
        if "local_dev_only" in line:
            continue
        for rule, pattern in RULES.items():
            if pattern.search(line):
                findings.append({"path": current, "line": number, "rule": rule})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    findings = scan_paths(candidate_paths(root))
    if args.history:
        findings.extend(scan_history(root))
    report = {"status": "PASS" if not findings else "FAIL", "findings": findings}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
