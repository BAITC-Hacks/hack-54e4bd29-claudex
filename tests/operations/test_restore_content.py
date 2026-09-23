from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.operations import common, restore_verify


def test_restore_rejects_existing_project_before_any_file_or_database_access(tmp_path):
    with pytest.raises(ValueError, match="phase8-"):
        restore_verify.restore_and_verify(tmp_path, "phase8-restore-test", "medsignal")


def test_legacy_backup_reports_incomplete_without_database_mutation(
    tmp_path, monkeypatch
):
    (tmp_path / "postgres.dump").write_bytes(b"synthetic")
    (tmp_path / "stores.json").write_text(json.dumps({"clickhouse_tables": []}))
    manifest = common.build_manifest(tmp_path, source_project="phase8-source")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    calls = []
    monkeypatch.setattr(restore_verify, "compose", lambda *a, **_k: calls.append(a))
    result = restore_verify.restore_and_verify(
        tmp_path, "phase8-restored", "phase8-target"
    )
    assert result["status"] == "RESTORE_VERIFICATION_INCOMPLETE"
    assert "postgres_inventory" in result["missing_evidence"]
    assert "minio_objects" in result["missing_evidence"]
    assert not calls


def test_manifest_does_not_accept_unlisted_restore_inputs(tmp_path):
    (tmp_path / "postgres.dump").write_bytes(b"synthetic")
    manifest = common.build_manifest(tmp_path, source_project="phase8-source")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "stores.json").write_text('{"changed":"unchecked"}')
    with pytest.raises(ValueError, match="manifest"):
        common.verify_manifest(tmp_path)


def _pg():
    return {
        "tables": {"alembic_version": 1, "synthetic_events": 3},
        "constraints": [
            {
                "table": "synthetic_events",
                "name": "events_pkey",
                "definition": "PRIMARY KEY (id)",
                "validated": True,
            }
        ],
        "alembic_versions": ["0008"],
    }


@pytest.mark.parametrize(
    "change", ["rows", "constraints", "validation", "migration", "missing_table"]
)
def test_pg_comparison_rejects_content_or_constraint_drift(change):
    assert hasattr(common, "verify_postgres_inventory")
    expected = _pg()
    actual = copy.deepcopy(expected)
    if change == "rows":
        actual["tables"]["synthetic_events"] = 2
    elif change == "constraints":
        actual["constraints"] = []
    elif change == "validation":
        actual["constraints"][0]["validated"] = False
    elif change == "migration":
        actual["alembic_versions"] = ["0007"]
    else:
        del actual["tables"]["synthetic_events"]
    with pytest.raises(RuntimeError, match="PostgreSQL.*mismatch"):
        common.verify_postgres_inventory(expected, actual)


def test_pg_exact_match_is_content_check_only():
    assert hasattr(common, "verify_postgres_inventory")
    common.verify_postgres_inventory(_pg(), copy.deepcopy(_pg()))


@pytest.mark.parametrize("change", ["same_size_corruption", "missing", "extra"])
def test_minio_comparison_checks_restored_bytes_not_only_counts(tmp_path, change):
    assert hasattr(common, "object_inventory")
    assert hasattr(common, "verify_object_inventory")
    bucket = tmp_path / "medsignal-artifacts"
    bucket.mkdir()
    artifact = bucket / "synthetic.bin"
    artifact.write_bytes(b"AAAA")
    expected = common.object_inventory(tmp_path, [bucket.name])
    if change == "same_size_corruption":
        artifact.write_bytes(b"BBBB")
    elif change == "missing":
        artifact.unlink()
    else:
        (bucket / "extra.bin").write_bytes(b"AAAA")
    with pytest.raises(RuntimeError, match="MinIO.*mismatch"):
        common.verify_object_inventory(
            expected, common.object_inventory(tmp_path, [bucket.name])
        )


def test_minio_empty_bucket_is_explicit_and_missing_bucket_is_failure(tmp_path):
    assert hasattr(common, "object_inventory")
    (tmp_path / "empty").mkdir()
    assert common.object_inventory(tmp_path, ["empty"]) == {"empty": {}}
    with pytest.raises(ValueError, match="bucket"):
        common.object_inventory(tmp_path, ["missing"])


def _complete_backup(tmp_path):
    from scripts.operations.backup import MINIO_BUCKETS

    (tmp_path / "postgres.dump").write_bytes(b"synthetic-pg")
    ch = tmp_path / "clickhouse"
    ch.mkdir()
    for name in ["schema_migrations", "synthetic_events"]:
        (ch / f"{name}.sql").write_text(
            f"CREATE TABLE synthetic.{name} (id UInt64) ENGINE=MergeTree ORDER BY id"
        )
        (ch / f"{name}.native").write_bytes(b"synthetic-ch")
    minio = tmp_path / "minio"
    for bucket in MINIO_BUCKETS:
        (minio / bucket).mkdir(parents=True)
    (minio / MINIO_BUCKETS[0] / "object.bin").write_bytes(b"AAAA")
    stores = {
        "verification_version": 2,
        "postgres_inventory": _pg(),
        "minio_objects": common.object_inventory(minio, list(MINIO_BUCKETS)),
        "minio_buckets": list(MINIO_BUCKETS),
        "clickhouse_database": "synthetic",
        "clickhouse_tables": ["schema_migrations", "synthetic_events"],
        "clickhouse_kinds": {"schema_migrations": "TABLE", "synthetic_events": "TABLE"},
        "clickhouse_checks": {
            name: {"expression": "count()", "value": 3}
            for name in ["schema_migrations", "synthetic_events"]
        },
        "clickhouse_migrations": [{"version": "006_synthetic", "checksum": "abc"}],
    }
    (tmp_path / "stores.json").write_text(json.dumps(stores))
    (tmp_path / "manifest.json").write_text(
        json.dumps(common.build_manifest(tmp_path, source_project="phase8-source"))
    )
    return stores


@pytest.mark.parametrize(
    "failure", [None, "pg_rows", "ch_checksum", "object_hash", "mirror_error"]
)
def test_restore_orchestration_gates_success_on_all_store_checks(
    tmp_path, monkeypatch, failure
):
    # A synthetic transport replaces unavailable Docker, not the verification logic.
    stores = _complete_backup(tmp_path)
    commands = []

    def fake_compose(_project, *args, **_kwargs):
        commands.append(args)
        mounts = [arg for arg in args if arg.endswith(":/verification")]
        if mounts:
            if failure == "mirror_error":
                raise RuntimeError("synthetic remote readback failure")
            output = Path(mounts[0].removesuffix(":/verification"))
            target = output / stores["minio_buckets"][0] / "object.bin"
            target.write_bytes(b"BBBB" if failure == "object_hash" else b"AAAA")
        return b""

    def fake_pg(*_args):
        actual = _pg()
        if failure == "pg_rows":
            actual["tables"]["synthetic_events"] = 2
        return actual

    def fake_ch(_project, query, input_bytes=None):
        if "SELECT version, checksum" in query:
            # schema_migrations is ordinary MergeTree, which rejects FINAL.
            assert "FINAL" not in query.upper().split(), query
            checksum = "changed" if failure == "ch_checksum" else "abc"
            return json.dumps({"version": "006_synthetic", "checksum": checksum}).encode()
        return b"3" if query.startswith("SELECT") else b""

    monkeypatch.setattr(restore_verify, "compose", fake_compose)
    monkeypatch.setattr(restore_verify, "postgres_inventory", fake_pg)
    monkeypatch.setattr(restore_verify, "_clickhouse", fake_ch)
    if failure:
        with pytest.raises(RuntimeError):
            restore_verify.restore_and_verify(
                tmp_path, "phase8-restored", "phase8-target"
            )
    else:
        result = restore_verify.restore_and_verify(
            tmp_path, "phase8-restored", "phase8-target"
        )
        assert result["status"] == "RESTORE_CONTENT_VERIFIED"
        assert result["application_workflow"] == "NOT_TESTED"
        assert result["rpo_rto_acceptance"] == "EXTERNAL_DEPENDENCY"
        assert result["postgres"]["rows_constraints_revisions"] == "MATCH"
        assert result["clickhouse"]["migration_checksums"] == "MATCH"
        assert result["minio"]["object_hashes"] == "MATCH"
        assert any(
            any(arg.endswith(":/verification") for arg in args) for args in commands
        )


def test_backup_records_pg_inventory_and_object_hashes(tmp_path, monkeypatch):
    from scripts.operations import backup

    inventories = []

    def fake_pg(_project):
        inventories.append(True)
        return _pg()

    def fake_compose(_project, *args, **_kwargs):
        if "run" in args:
            path = Path(args[args.index("--volume") + 1].removesuffix(":/backup"))
            (path / backup.MINIO_BUCKETS[0] / "object.bin").write_bytes(b"AAAA")
        return b"synthetic-pg"

    def fake_ch(_project, query):
        if "currentDatabase" in query:
            return b"synthetic"
        if "SHOW TABLES" in query:
            return b"schema_migrations"
        if "SHOW CREATE" in query:
            return b"CREATE TABLE synthetic.schema_migrations (id UInt64) ENGINE=Memory"
        if "version, checksum" in query:
            # schema_migrations is ordinary MergeTree, which rejects FINAL.
            assert "FINAL" not in query.upper().split(), query
            return b'{"version":"006_synthetic","checksum":"abc"}'
        if "count()" in query:
            return b"1"
        return b"synthetic-native"

    monkeypatch.setattr(backup, "postgres_inventory", fake_pg)
    monkeypatch.setattr(backup, "compose", fake_compose)
    monkeypatch.setattr(backup, "_clickhouse", fake_ch)
    target = tmp_path / "new-backup"
    backup.create_backup(target, "phase8-source")
    assert len(inventories) == 2
    common.verify_manifest(target)
    stores = json.loads((target / "stores.json").read_text())
    assert stores["postgres_inventory"] == _pg()
    assert stores["minio_objects"][backup.MINIO_BUCKETS[0]]["object.bin"][
        "sha256"
    ] == common.sha256_file(target / "minio" / backup.MINIO_BUCKETS[0] / "object.bin")
    assert stores["clickhouse_migrations"] == [
        {"version": "006_synthetic", "checksum": "abc"}
    ]


def test_nested_object_named_manifest_is_verified(tmp_path):
    objects = tmp_path / "minio" / "medsignal-artifacts"
    objects.mkdir(parents=True)
    (objects / "manifest.json").write_text('{"synthetic":true}')
    (tmp_path / "manifest.json").write_text(
        json.dumps(common.build_manifest(tmp_path, source_project="phase8-source"))
    )
    common.verify_manifest(tmp_path)
