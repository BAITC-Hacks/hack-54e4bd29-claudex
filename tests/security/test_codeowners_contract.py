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
        if pattern.startswith("/") and pattern.endswith("/"):
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
        "backend/app/main.py": "@zzhassyn",
        "backend/alembic/versions/0001.sql": "@zzhassyn",
        "data_pipeline/cli.py": "@zzhassyn",
        "ml/training/train.py": "@zzhassyn",
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
    }
    for path, expected_owner in expected.items():
        assert _owner(path) == expected_owner, path


def test_extra_account_is_not_automatically_assigned() -> None:
    content = (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
    assert "@albqqd" not in content
