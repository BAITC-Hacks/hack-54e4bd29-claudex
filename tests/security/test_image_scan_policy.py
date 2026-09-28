"""Behavioral tests for the current-image vulnerability admission gate."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from scripts.security.image_scan import evaluate_scan, main


def test_image_scan_does_not_import_python311_only_datetime_utc() -> None:
    source = Path("scripts/security/image_scan.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    datetime_imports = [
        alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module == "datetime"
        for alias in node.names
    ]
    assert "UTC" not in datetime_imports


def _image(*findings: tuple[str, str]) -> dict[str, object]:
    return {
        "image": "medsignal-backend:ci",
        "image_id": "sha256:" + "a" * 64,
        "repo_digests": [],
        "vulnerabilities": [
            {
                "vulnerability_id": identifier,
                "severity": severity,
                "package": "synthetic-package",
                "installed_version": "1.0",
                "fixed_version": None,
            }
            for identifier, severity in findings
        ],
    }


def _acceptance(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "image": "medsignal-backend:ci",
        "image_id": "sha256:" + "a" * 64,
        "vulnerability_ids": ["CVE-2099-0001"],
        "owner": "Synthetic security owner",
        "approval_reference": "SYNTHETIC-1",
        "rationale": "Synthetic test acceptance only",
        "expires_on": "2099-12-31",
    }
    item.update(overrides)
    return {"acceptances": [item]}


def test_critical_finding_fails_even_if_acceptance_mentions_it() -> None:
    result = evaluate_scan(
        [_image(("CVE-2099-0001", "CRITICAL"))],
        _acceptance(),
        today=date(2099, 1, 1),
    )
    assert result["passed"] is False
    assert result["images"][0]["critical"] == 1


def test_high_finding_fails_without_exact_documented_digest_and_cve() -> None:
    image = _image(("CVE-2099-0001", "HIGH"))
    assert (
        evaluate_scan([image], {"acceptances": []}, today=date(2099, 1, 1))["passed"]
        is False
    )
    assert (
        evaluate_scan(
            [image], _acceptance(image_id="sha256:" + "b" * 64), today=date(2099, 1, 1)
        )["passed"]
        is False
    )
    assert (
        evaluate_scan(
            [image],
            _acceptance(vulnerability_ids=["CVE-2099-9999"]),
            today=date(2099, 1, 1),
        )["passed"]
        is False
    )


def test_expired_or_unowned_high_acceptance_fails_closed() -> None:
    image = _image(("CVE-2099-0001", "HIGH"))
    assert (
        evaluate_scan(
            [image], _acceptance(expires_on="2098-12-31"), today=date(2099, 1, 1)
        )["passed"]
        is False
    )
    assert (
        evaluate_scan([image], _acceptance(owner=""), today=date(2099, 1, 1))["passed"]
        is False
    )


def test_exact_high_acceptance_keeps_findings_visible_in_report() -> None:
    result = evaluate_scan(
        [_image(("CVE-2099-0001", "HIGH"))],
        _acceptance(),
        today=date(2099, 1, 1),
    )
    assert result["passed"] is True
    assert result["images"][0]["high"] == 1
    assert result["images"][0]["findings"][0]["vulnerability_id"] == "CVE-2099-0001"
    assert result["images"][0]["findings"][0]["accepted"] is True


def test_only_complete_acceptance_covers_multiple_high_findings() -> None:
    result = evaluate_scan(
        [_image(("CVE-2099-0001", "HIGH"), ("CVE-2099-0002", "HIGH"))],
        _acceptance(),
        today=date(2099, 1, 1),
    )
    assert result["passed"] is False
    assert result["images"][0]["unaccepted_high"] == 1


def test_clean_image_passes_without_acceptance() -> None:
    result = evaluate_scan([_image()], {"acceptances": []}, today=date(2099, 1, 1))
    assert result["passed"] is True
    assert result["images"][0]["high"] == 0


def test_malformed_acceptance_cannot_authorize_high_findings() -> None:
    result = evaluate_scan(
        [_image(("CVE-2099-0001", "HIGH"))],
        _acceptance(vulnerability_ids="CVE-2099-0001"),
        today=date(2099, 1, 1),
    )
    assert result["passed"] is False


def test_truncated_image_digest_is_rejected() -> None:
    image = _image()
    image["image_id"] = "sha256:a"
    with pytest.raises(ValueError, match="content digest"):
        evaluate_scan([image], {"acceptances": []}, today=date(2099, 1, 1))


def test_missing_manifest_writes_failing_machine_artifact(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = main(
        [
            "--image",
            "synthetic-image:ci",
            "--output",
            str(report),
            "--acceptance",
            str(tmp_path / "missing.json"),
        ]
    )
    assert code == 2
    assert '"passed": false' in report.read_text(encoding="utf-8")
    assert "FAIL" in report.with_suffix(".md").read_text(encoding="utf-8")
