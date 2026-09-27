"""Scan project-built MinIO images without a Docker socket in the scanner.

The machine scan and CycloneDX SBOM stay in ignored project-scoped tmp files.
HIGH findings allow only synthetic functional verification; CRITICAL findings
or missing Go inventory stop startup. This is not production risk acceptance.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any

from scripts.operations.minio_source_build import BUILD_ROOT, load_built_images
from scripts.operations.prepare_acceptance import ROOT, validate_project_name
from scripts.security.image_scan import TRIVY_IMAGE


def classify_scan(scan: dict[str, Any], sbom: dict[str, Any]) -> dict[str, Any]:
    """Keep security admission separate from functional acceptance."""
    results = scan.get("Results") or []
    components = sbom.get("components") or []
    vulnerabilities = [
        item
        for result in results
        if isinstance(result, dict)
        for item in result.get("Vulnerabilities") or []
        if isinstance(item, dict)
    ]
    high = sum(item.get("Severity") == "HIGH" for item in vulnerabilities)
    critical = sum(item.get("Severity") == "CRITICAL" for item in vulnerabilities)
    go_components = [
        item
        for item in components
        if isinstance(item, dict)
        and isinstance(item.get("purl"), str)
        and item["purl"].startswith("pkg:golang/")
    ]
    go_results = [
        item
        for item in results
        if isinstance(item, dict)
        and (item.get("Class") == "lang-pkgs" or item.get("Type") == "gobinary")
    ]
    detected = bool(go_components)
    os_components = [
        item
        for item in components
        if isinstance(item, dict)
        and isinstance(item.get("purl"), str)
        and item["purl"].startswith("pkg:apk/")
    ]
    return {
        "high": high,
        "critical": critical,
        "go_components_detected": detected,
        "go_component_count": len(go_components),
        "os_package_count": len(os_components),
        "critical_findings": [
            {
                "id": item.get("VulnerabilityID"),
                "package": item.get("PkgName"),
                "installed_version": item.get("InstalledVersion"),
                "fixed_version": item.get("FixedVersion"),
            }
            for item in vulnerabilities
            if item.get("Severity") == "CRITICAL"
        ],
        "go_vulnerability_targets": len(go_results),
        "go_stdlib_detected": any(item.get("name") == "stdlib" for item in go_components),
        "security_admission": "NOT VERIFIED"
        if not detected
        else "FAIL"
        if high or critical
        else "PASS",
        "functional_may_continue": detected and critical == 0,
    }


def parse_scanner_version(output: str) -> tuple[str, str | None, str | None]:
    """Read scanner and cached DB metadata without copying raw CLI text."""
    match = re.search(r"Version:\s*([0-9]+(?:\.[0-9]+){2})", output)
    db_match = re.search(r"UpdatedAt:\s*([^\n]+)", output)
    db_version = re.search(r"Vulnerability DB:\s*Version:\s*([^\n]+)", output)
    return (
        match.group(1) if match else "NOT AVAILABLE",
        db_match.group(1).strip() if db_match else None,
        db_version.group(1).strip() if db_version else None,
    )


def _run(args: list[str], *, timeout: int = 900) -> str:
    try:
        result = subprocess.run(  # noqa: S603 — fixed Docker CLI arguments
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("MinIO scan command unavailable") from exc
    if result.returncode:
        raise RuntimeError("MinIO scan command failed")
    return result.stdout


def scan(project: str) -> dict[str, Any]:
    """Produce per-image vulnerability JSON and SBOM, then gate startup."""
    validate_project_name(project)
    images = load_built_images(project)
    output = BUILD_ROOT / project / "security"
    output.mkdir(exist_ok=False)
    cache = f"{project}_minio-trivy-cache"
    rows: dict[str, dict[str, Any]] = {}
    scanner_version = "NOT AVAILABLE"
    database_updated_at: str | None = None
    database_version: str | None = None
    try:
        for name, image_id in images.items():
            archive = output / f"{name}.tar"
            _run(["docker", "image", "save", "--output", str(archive), image_id])
            mount = f"type=bind,source={output.resolve()},target=/evidence,readonly"
            common = [
                "docker",
                "run",
                "--rm",
                "--mount",
                mount,
                "--mount",
                f"type=volume,source={cache},target=/root/.cache/trivy",
                TRIVY_IMAGE,
                "image",
                "--input",
                f"/evidence/{name}.tar",
            ]
            raw_scan = _run(
                [*common, "--scanners", "vuln", "--format", "json"], timeout=1800
            )
            raw_sbom = _run([*common, "--format", "cyclonedx"], timeout=1800)
            (output / f"{name}-trivy.json").write_text(raw_scan, encoding="utf-8")
            (output / f"{name}-sbom.cdx.json").write_text(raw_sbom, encoding="utf-8")
            rows[name] = classify_scan(json.loads(raw_scan), json.loads(raw_sbom))
            archive.unlink()
            print(
                f"MinIO {name} scan: HIGH={rows[name]['high']} "
                f"CRITICAL={rows[name]['critical']} "
                f"Go components={rows[name]['go_component_count']}"
            )
        version_text = _run(
            [
                "docker",
                "run",
                "--rm",
                "--mount",
                f"type=volume,source={cache},target=/root/.cache/trivy",
                TRIVY_IMAGE,
                "--version",
            ]
        )
        scanner_version, database_updated_at, database_version = parse_scanner_version(
            version_text
        )
    finally:
        # This cache belongs only to this phase8-* project, never an existing stack.
        subprocess.run(  # noqa: S603 — scoped Docker CLI cleanup
            ["docker", "volume", "rm", cache],  # noqa: S607 — fixed Docker CLI
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
    report = {
        "project": project,
        "scanner": "Trivy",
        "scanner_image": TRIVY_IMAGE,
        "scanner_version": scanner_version,
        "vulnerability_database_updated_at": database_updated_at,
        "vulnerability_database_version": database_version,
        "images": rows,
        "functional_acceptance_allowed": all(
            row["functional_may_continue"] for row in rows.values()
        ),
        "security_admission": "FAIL",
        "security_admission_reason": (
            "PATCHED_ACCEPTANCE is not a supported production storage path"
        ),
    }
    (output / "scan-summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args(argv)
    try:
        report = scan(args.project)
        if not report["functional_acceptance_allowed"]:
            print("MinIO scan blocked functional startup", file=sys.stderr)
            return 2
        print("MinIO synthetic functional startup allowed; see security verdict")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"MinIO scan: FAIL ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
