"""Protect the agreed team ownership boundaries from accidental reassignment."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _owner(path: str) -> str | None:
    """Resolve the last matching GitHub CODEOWNERS rule for representative paths."""
    owner = None
    for raw_line in (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        pattern, *owners = line.split()
        assert len(owners) == 1, f"Ambiguous CODEOWNERS line: {pattern}"
        if pattern == "*":
            matches = True
        elif pattern.startswith("/") and pattern.endswith("/"):
            matches = path.startswith(pattern[1:])
        elif pattern.startswith("/"):
            matches = fnmatchcase("/" + path, pattern)
        else:
            matches = fnmatchcase(path.rsplit("/", 1)[-1], pattern)
        if matches:
            owner = owners[0]
    return owner


def test_zone_ownership_and_explicit_file_exceptions() -> None:
    expected = {
        "README.md": "@Alim-Rakhmet",
        ".env.example": "@Alim-Rakhmet",
        ".importlinter": "@zzhassyn",
        "backend/app/main.py": "@zzhassyn",
        "backend/alembic/versions/0001.sql": "@zzhassyn",
        "data_pipeline/cli.py": "@zzhassyn",
        "ml/training/train.py": "@zzhassyn",
        "pilot/monitoring.py": "@zzhassyn",
        "data/audit/medsignal_audit_summary.json": "@zzhassyn",
        "database/clickhouse/migrations/001.sql": "@zzhassyn",
        "backend/requirements.txt": "@zzhassyn",
        "infrastructure/nginx/nginx.conf": "@Alim-Rakhmet",
        ".github/workflows/ci.yml": "@Alim-Rakhmet",
        "docker-compose.production.yml": "@Alim-Rakhmet",
        "backend/Dockerfile": "@Alim-Rakhmet",
        "frontend/Dockerfile": "@Alim-Rakhmet",
        "infrastructure/docker/mlflow.Dockerfile": "@Alim-Rakhmet",
        "frontend/src/app/page.tsx": "@aldabergenuly",
        "frontend/package.json": "@aldabergenuly",
        "frontend/package-lock.json": "@aldabergenuly",
        "tests/audit/test_audit.py": "@zzhassyn",
        "tests/pipeline/test_loading.py": "@zzhassyn",
        "tests/monitoring/test_monitoring.py": "@zzhassyn",
        "tests/e2e/test_workflow_race_contract.py": "@zzhassyn",
        "tests/e2e/test_phase8_contract.py": "@Alim-Rakhmet",
        "tests/performance/test_background_jobs.py": "@zzhassyn",
        "tests/performance/test_benchmark_statistics.py": "@Alim-Rakhmet",
        "tests/security/test_real_keycloak_roles.py": "@zzhassyn",
        "tests/security/test_codeowners_contract.py": "@Alim-Rakhmet",
        "scripts/phase8_e2e.py": "@zzhassyn",
        "scripts/phase7-smoke.sh": "@zzhassyn",
        "scripts/performance/verify_analytics.py": "@zzhassyn",
        "scripts/performance/benchmark.py": "@Alim-Rakhmet",
        "scripts/operations/backup.py": "@Alim-Rakhmet",
        "docs/API.md": "@zzhassyn",
        "docs/analytics/CURRENT_MAIN_VALIDATION.md": "@zzhassyn",
        "docs/analytics/SITUATION_CENTER.md": "@aldabergenuly",
        "docs/acceptance/SHADOW_PILOT_REPORT.md": "@zzhassyn",
        "docs/acceptance/PILOT_BASELINE.md": "@Alim-Rakhmet",
        "docs/runbooks/DEMO.md": "@aldabergenuly",
        "docs/frontend/USER_JOURNEY_AUDIT.md": "@aldabergenuly",
        "docs/ADR/0001-modular-monolith.md": "@zzhassyn",
        "docs/ADR/0006-security-architecture.md": "@Alim-Rakhmet",
        "docs/TEAM_OWNERSHIP.md": "@Alim-Rakhmet",
    }
    for path, expected_owner in expected.items():
        assert _owner(path) == expected_owner, path


def test_extra_account_is_not_automatically_assigned() -> None:
    content = (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
    assert "@albqqd" not in content
