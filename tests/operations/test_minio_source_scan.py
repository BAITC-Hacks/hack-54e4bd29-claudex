"""HIGH does not become a security pass; CRITICAL blocks startup."""

from __future__ import annotations

from scripts.operations.minio_source_scan import classify_scan


def _sbom() -> dict[str, object]:
    return {"components": [{"purl": "pkg:golang/github.com/minio/minio@v0"}]}


def test_high_is_recorded_but_is_not_security_admission() -> None:
    raw = {
        "Results": [
            {
                "Class": "lang-pkgs",
                "Type": "gobinary",
                "Vulnerabilities": [
                    {"Severity": "HIGH", "VulnerabilityID": "CVE-SYNTHETIC"}
                ],
            }
        ]
    }
    result = classify_scan(raw, _sbom())
    assert result["high"] == 1
    assert result["critical"] == 0
    assert result["go_components_detected"] is True
    assert result["security_admission"] == "FAIL"
    assert result["functional_may_continue"] is True


def test_critical_blocks_functional_start() -> None:
    raw = {
        "Results": [
            {"Vulnerabilities": [{"Severity": "CRITICAL", "VulnerabilityID": "CVE-X"}]}
        ]
    }
    result = classify_scan(raw, _sbom())
    assert result["critical"] == 1
    assert result["functional_may_continue"] is False


def test_missing_go_components_is_not_a_clean_scan() -> None:
    result = classify_scan({"Results": []}, {"components": []})
    assert result["go_components_detected"] is False
    assert result["security_admission"] == "NOT VERIFIED"
    assert result["functional_may_continue"] is False
