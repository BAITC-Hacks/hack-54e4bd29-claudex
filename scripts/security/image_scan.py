"""Scan built container images and enforce an explicit vulnerability gate.

The scanner receives an exported image archive, never the Docker socket.
Only reviewed HIGH findings for the exact image ID may pass; CRITICAL is fatal.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

TRIVY_IMAGE = (
    "aquasec/trivy:0.58.2@sha256:"
    "665030f4d33a82c1e8d9d5e0453365842236723c1ee5cc3becca698268e66a56"
)
CACHE_VOLUME = "medsignal-ci-trivy-cache"


def _accepted_high(
    *,
    image: str,
    image_id: str,
    vulnerability_id: str,
    acceptances: list[dict[str, Any]],
    today: date,
) -> bool:
    for item in acceptances:
        if item.get("image") != image or item.get("image_id") != image_id:
            continue
        ids = item.get("vulnerability_ids")
        if not isinstance(ids, list) or vulnerability_id not in ids:
            continue
        if not all(
            isinstance(item.get(field), str) and item[field].strip()
            for field in ("owner", "approval_reference", "rationale", "expires_on")
        ):
            continue
        try:
            expires_on = date.fromisoformat(item["expires_on"])
        except ValueError:
            continue
        if expires_on >= today:
            return True
    return False


def evaluate_scan(
    images: list[dict[str, Any]], acceptance: dict[str, Any], *, today: date | None = None
) -> dict[str, Any]:
    """Return a lossless HIGH/CRITICAL finding summary and fail-closed decision."""
    current_date = today or date.today()
    entries = acceptance.get("acceptances", [])
    if not isinstance(entries, list) or not all(isinstance(x, dict) for x in entries):
        raise ValueError("Invalid image-risk acceptance manifest")
    summary: list[dict[str, Any]] = []
    for image in images:
        image_id = image.get("image_id")
        if (
            not isinstance(image_id, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
        ):
            raise ValueError("Scanned image has no content digest")
        findings = []
        for item in image.get("vulnerabilities", []):
            if item.get("severity") not in {"HIGH", "CRITICAL"}:
                continue
            finding = dict(item)
            finding["accepted"] = finding["severity"] == "HIGH" and _accepted_high(
                image=image["image"],
                image_id=image_id,
                vulnerability_id=finding["vulnerability_id"],
                acceptances=entries,
                today=current_date,
            )
            findings.append(finding)
        high = sum(x["severity"] == "HIGH" for x in findings)
        critical = sum(x["severity"] == "CRITICAL" for x in findings)
        unaccepted_high = sum(
            x["severity"] == "HIGH" and not x["accepted"] for x in findings
        )
        summary.append(
            {
                "image": image["image"],
                "image_id": image_id,
                "repo_digests": image.get("repo_digests", []),
                "high": high,
                "critical": critical,
                "unaccepted_high": unaccepted_high,
                "findings": findings,
            }
        )
    return {
        "passed": bool(summary)
        and all(
            item["critical"] == 0 and item["unaccepted_high"] == 0 for item in summary
        ),
        "images": summary,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# MedSignal current-image vulnerability scan",
        "",
        f"Scanner: `{report['scanner']}`; generated: `{report['generated_at']}`.",
        f"Gate: **{'PASS' if report['passed'] else 'FAIL'}**. "
        "CRITICAL always fails; HIGH requires exact documented acceptance.",
        "",
    ]
    for image in report["images"]:
        lines.extend(
            [
                f"## {image['image']}",
                "",
                f"Image content ID: `{image['image_id']}`",
                f"HIGH: {image['high']}; CRITICAL: {image['critical']}; "
                f"unaccepted HIGH: {image['unaccepted_high']}.",
                "",
                "| Severity | Vulnerability | Package | Installed | Fixed | Accepted |",
                "|---|---|---|---|---|---|",
            ]
        )
        for finding in image["findings"]:
            fields = [
                finding["severity"],
                finding["vulnerability_id"],
                finding.get("package") or "—",
                finding.get("installed_version") or "—",
                finding.get("fixed_version") or "—",
                "yes" if finding["accepted"] else "no",
            ]
            lines.append(
                "| " + " | ".join(str(x).replace("|", "\\|") for x in fields) + " |"
            )
        lines.append("")
    return "\n".join(lines)


def _run(
    command: list[str], *, stdout: Any = subprocess.PIPE
) -> subprocess.CompletedProcess[str]:
    # Commands are fixed Docker argv vectors constructed here; shell=False.
    return subprocess.run(  # noqa: S603
        command, check=True, text=True, stdout=stdout, stderr=sys.stderr
    )


def _scan_image(image: str, output_dir: Path) -> dict[str, Any]:
    inspect = json.loads(_run(["docker", "image", "inspect", image]).stdout)[0]
    with tempfile.TemporaryDirectory(prefix="medsignal-image-scan-") as temporary:
        archive = Path(temporary) / "image.tar"
        _run(["docker", "image", "save", "-o", str(archive), image])
        scan = _run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--mount",
                f"type=bind,source={temporary},target=/evidence,readonly",
                "-v",
                f"{CACHE_VOLUME}:/root/.cache/trivy",
                TRIVY_IMAGE,
                "image",
                "--skip-db-update",
                "--skip-java-db-update",
                "--offline-scan",
                "--ignorefile",
                "/dev/null",
                "--scanners",
                "vuln",
                "--format",
                "json",
                "--timeout",
                "10m",
                "--input",
                "/evidence/image.tar",
            ]
        )
    parsed = json.loads(scan.stdout)
    safe_name = image.split(":")[0].replace("/", "-")
    (output_dir / f"trivy-{safe_name}.json").write_text(scan.stdout, encoding="utf-8")
    vulnerabilities = [
        {
            "vulnerability_id": item["VulnerabilityID"],
            "severity": item["Severity"],
            "package": item.get("PkgName"),
            "installed_version": item.get("InstalledVersion"),
            "fixed_version": item.get("FixedVersion"),
        }
        for target in parsed.get("Results", [])
        for item in target.get("Vulnerabilities") or []
    ]
    return {
        "image": image,
        "image_id": inspect["Id"],
        "repo_digests": inspect.get("RepoDigests") or [],
        "vulnerabilities": vulnerabilities,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--acceptance",
        type=Path,
        default=Path("docs/security/image-risk-acceptance.json"),
    )
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        acceptance = json.loads(args.acceptance.read_text(encoding="utf-8"))
        version = _run(["docker", "run", "--rm", TRIVY_IMAGE, "--version"]).stdout.strip()
        _run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{CACHE_VOLUME}:/root/.cache/trivy",
                TRIVY_IMAGE,
                "image",
                "--download-db-only",
            ]
        )
        images = [_scan_image(image, args.output.parent) for image in args.image]
        report = evaluate_scan(images, acceptance)
        report["scanner"] = f"{TRIVY_IMAGE} ({version})"
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        args.output.with_suffix(".md").write_text(
            _render_markdown(report), encoding="utf-8"
        )
        print(
            f"Trivy gate: {'PASS' if report['passed'] else 'FAIL'}; report: {args.output}"
        )
        return 0 if report["passed"] else 1
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        # Failure to build scan evidence must never be interpreted as a clean scan.
        error_name = type(exc).__name__
        args.output.write_text(
            json.dumps({"passed": False, "scan_error": error_name}, indent=2) + "\n",
            encoding="utf-8",
        )
        args.output.with_suffix(".md").write_text(
            "# MedSignal image scan — FAIL\n\n"
            f"Scan evidence is incomplete ({error_name}). No image is admitted.\n",
            encoding="utf-8",
        )
        print(
            f"Trivy gate: FAIL ({error_name}); report: {args.output}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
