from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.operations.common import (
    build_manifest,
    clickhouse_verification_expression,
    require_phase8_namespace,
    verify_manifest,
)
from scripts.operations.restore_verify import _is_materialized_view


@pytest.mark.parametrize("value", ["phase8-restore", "phase8-demo-01"])
def test_phase8_namespace_is_accepted(value: str) -> None:
    assert require_phase8_namespace(value) == value


@pytest.mark.parametrize("value", ["medsignal", "phase7-test", "phase8", "../phase8-x"])
def test_non_phase8_namespace_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="phase8-"):
        require_phase8_namespace(value)


def test_manifest_detects_changed_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "postgres.dump"
    artifact.write_bytes(b"accepted")
    manifest = build_manifest(tmp_path, source_project="medsignal")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    verify_manifest(tmp_path)
    artifact.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        verify_manifest(tmp_path)


def test_manifest_never_includes_itself_or_redis(tmp_path: Path) -> None:
    (tmp_path / "postgres.dump").write_bytes(b"pg")
    (tmp_path / "clickhouse").mkdir()
    (tmp_path / "clickhouse" / "table.native").write_bytes(b"ch")
    manifest = build_manifest(tmp_path, source_project="medsignal")
    paths = {item["path"] for item in manifest["artifacts"]}
    assert "manifest.json" not in paths
    assert all("redis" not in path.lower() for path in paths)


def test_materialized_view_is_restored_after_stateful_tables() -> None:
    assert _is_materialized_view(
        "CREATE MATERIALIZED VIEW db.mv TO db.target AS SELECT 1"
    )
    assert not _is_materialized_view(
        "CREATE TABLE db.fact (id UInt64) ENGINE=MergeTree ORDER BY id"
    )


def test_clickhouse_restore_uses_semantic_aggregate_checks() -> None:
    assert (
        clickhouse_verification_expression("agg_referrals_daily", "TABLE")
        == "sum(referrals)"
    )
    assert (
        clickhouse_verification_expression("agg_refusals_daily", "TABLE")
        == "sum(refusals)"
    )
    assert clickhouse_verification_expression("fact_waiting_events", "TABLE") == "count()"
    assert (
        clickhouse_verification_expression("mv_referrals_daily", "MATERIALIZED_VIEW")
        is None
    )
