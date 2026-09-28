# Pilot recovery recheck — 2026-09-24

**Result: RESTORE_CONTENT_VERIFIED**, executed on Docker Engine **29.8.0** using synthetic data only. This proves store recovery for these fixtures. It does not establish actual pilot RPO/RTO or production recovery readiness. The parent also completed a separate restored-application readback with **PASS**, documented below.

## Scope and isolation

- Worktree: `C:/Users/zhasy/.codex/worktrees/medsignal-reproducibility/govtech_case1`; baseline `78d5f8c`; branch `codex/pilot-reproducibility`.
- Source project: `phase8-runtime-20260924`, with new isolated volumes. Source PostgreSQL and ClickHouse database names are both `phase8-runtime-20260924`.
- Configuration: absolute root `docker-compose.yml` plus `artifacts/phase8-runtime-20260924/compose.isolated.yml`; secrets loaded internally from `.env.phase8` in that artifact directory.
- Parent sent `FIXTURES_READY` after its synthetic OIDC/workflow/restart tests, then stopped only isolated backend, worker and mlflow. Preflight recorded these as exited; they remained stopped through restore. Independent database tests used other databases.
- No actual data import or training. No current `medsignal` project resources modified or cleaned. No accepted migrations changed. No commit, push or subagents by this task.
- Only source-persistent write by recovery: one approved synthetic MinIO object. PostgreSQL canonicalization creates transaction-local temporary tables and rolls back.

## Exact executed commands and configuration

Commands ran from the worktree above. Ignored runners and logs are retained under `artifacts/phase8-runtime-20260924-restore/`.

```powershell
$env:PYTHONUTF8='1'
& .venv/Scripts/python.exe artifacts/phase8-runtime-20260924-restore/run_recovery.py preflight
& .venv/Scripts/python.exe -m pytest tests/operations -q --basetemp artifacts/phase8-runtime-20260924-restore/pytest-baseline
# After FIXTURES_READY and confirmed stopped writers:
& .venv/Scripts/python.exe artifacts/phase8-runtime-20260924-restore/run_recovery.py backup
& .venv/Scripts/python.exe artifacts/phase8-runtime-20260924-restore/run_recovery.py restore --namespace phase8-restore-20260924-a
# First restore detected the CHECK representation mismatch described below.
# After the regression test and fix, create a NEW backup:
& .venv/Scripts/python.exe artifacts/phase8-runtime-20260924-restore/run_recheck.py backup
& .venv/Scripts/python.exe artifacts/phase8-runtime-20260924-restore/run_recheck.py restore
```

The runner parses the parent-generated literal KEY=VALUE env file internally, without shell evaluation or printing its values, and sets these before importing the operations modules:

```python
os.environ.update(values_from_phase8_env_file)
os.environ['COMPOSE_FILE'] = os.pathsep.join([
    str(ROOT / 'docker-compose.yml'),
    str(ROOT / 'artifacts/phase8-runtime-20260924/compose.isolated.yml'),
])
os.environ['COMPOSE_ENV_FILES'] = str(ROOT / 'artifacts/phase8-runtime-20260924/.env.phase8')
os.environ['COMPOSE_PROJECT_DIRECTORY'] = str(ROOT)
os.environ['COMPOSE_PATH_SEPARATOR'] = os.pathsep
os.environ['COMPOSE_PROJECT_NAME'] = 'phase8-runtime-20260924'
```

ROOT is the absolute worktree. Preflight reads Compose configuration without displaying it, requires the exact project, rejects external authoritative-store volumes, checks their names have the source project prefix, and verifies container project labels. The transport guard permits only that exact project. Logs contain operation/service/duration/exit summaries without credentials, query results or object contents.

The successful recheck invokes the production functions:

```python
create_backup(OUT / 'backup-canonical', 'phase8-runtime-20260924')
restore_and_verify(
    OUT / 'backup-canonical',
    'phase8-restore-20260924-b',
    'phase8-runtime-20260924',
)
```

OUT is the absolute recovery artifact directory. Both recheck actions require readiness and exited writers. The existing synthetic object is reused, with no second source write. Both backup directories and the first PostgreSQL restore target are retained; a rerun needs a fresh output directory and namespace.

## Data types and results

All application data is synthetic: access subjects/scopes, directory records, monitoring signals, a forecast with points, a closed incident, actions, a scenario and audit events. The data-import row is synthetic lineage metadata, not a real source file import. No trained or admitted model is claimed.

| Store | Actual backup and content | Executed verification |
| --- | --- | --- |
| PostgreSQL | Custom-format pg_dump; 25 public tables; 89 constraints; Alembic `0008_mapping_versions` | Exact per-table counts, full constraint definitions/names/validation flags and revision inventory match after pg_restore --exit-on-error |
| ClickHouse | Native plus DDL for 12 stateful tables; DDL-only restore for 2 materialized views | 30 referral facts; sum(referrals)=30; sum(refusals)=0; all stateful checks and all 6 ordered migration version/checksum pairs match |
| MinIO | 8 bucket inventories: 7 empty, 1 containing a synthetic binary object | Downloaded all restored objects again through the target API; complete key/size/SHA-256 inventories match |
| Redis | Excluded | Non-authoritative queue/cache; no recovery claim |

Nonempty PostgreSQL counts: users 6; user data scopes 6; regions 2; hospitals 3; signals 6; signal explanations 5; forecasts 1; forecast points 7; incidents 1; actions 4; scenarios 1; audit events 5; data imports 1; mapping state 1; Alembic version 1. Other tables are empty, including model versions. Final read-only comparison confirmed source PostgreSQL inventory was unchanged from the successful backup.

ClickHouse DDL includes Date/DateTime64(3), String/LowCardinality(String), Nullable fields, UUID and UInt64, with MergeTree facts and SummingMergeTree aggregates. Views are created after stateful data restore to prevent aggregate replay/double counting. Aggregate verification uses sums, stable across background merges, rather than relying on physical aggregate row counts.

Object key: `phase8-recovery/synthetic-recovery.bin`. Content: synthetic-only label plus bytes 0–255. Size: **330 bytes**. SHA-256:

```text
5401ae0d4eb03795418d8eaa36fcdf2b9f024aff38bc2d881ef74b6d3c2ce8fd
```

## Runtime defects and red/green proof

1. **Hyphenated ClickHouse source name rejected.** SHOW CREATE TABLE correctly backtick-quotes the source name, but restore applied the stricter table-name allowlist to database names. A separate database allowlist permits safe hyphens. Target names still derive from validated phase8 namespaces; backticks, semicolons, spaces and traversal remain rejected before writes. Regression RED: 5 failures / 34 passes; GREEN: 39 passes. Actual restore exercised hyphenated source and underscore target names.
2. **PostgreSQL CHECK deparse changes during dump/restore.** The system_operations status CHECK moved a varchar-to-text array cast onto individual elements. Counts and revision matched, but raw definitions differed. The inventory now reparses each CHECK on an empty temporary table with source column types and reads the server-canonical definition. All casts, names and original validation flags remain; other constraints, counts and revisions still compare exactly. A real pg_dump/pg_restore regression failed before the fix and passed after it. The same test adds an extra allowed status and proves genuine constraint drift still fails. Temporary normalization objects roll back; the regression deletes only its two uniquely named phase8_ops_* databases.

First target `phase8_restore_20260924_a_postgres` is retained as failed-at-verification evidence; ClickHouse/MinIO were not reached on that attempt. A fresh, independently checksummed backup with canonical inventory was restored to namespace b. The initial backup manifest was not edited.

Final validation commands:

```powershell
# Real PostgreSQL regression was run RED then GREEN:
& .venv/Scripts/python.exe artifacts/phase8-runtime-20260924-restore/run_live_test.py
# Full operations suite with the live regression enabled:
@'
import runpy, os, pytest
runpy.run_path('artifacts/phase8-runtime-20260924-restore/run_recovery.py')
os.environ['OPERATIONS_TEST_PROJECT']='phase8-runtime-20260924'
raise SystemExit(pytest.main(['tests/operations','-q','--basetemp','artifacts/phase8-runtime-20260924-restore/pytest-final']))
'@ | & .venv/Scripts/python.exe -
& .venv/Scripts/python.exe -m ruff check scripts/operations/common.py scripts/operations/restore_verify.py tests/operations/test_restore_content.py tests/operations/test_postgres_roundtrip.py
& .venv/Scripts/python.exe -m ruff format --check scripts/operations/common.py scripts/operations/restore_verify.py tests/operations/test_restore_content.py tests/operations/test_postgres_roundtrip.py
```

Result: **40 passed**, including the real PostgreSQL regression. Lint and formatting passed. Application, broader DB and build checks belong to the parent and other assigned worker.

## RESTORE_READY handoff

All targets are within the existing isolated Compose project `phase8-runtime-20260924`:

- Namespace: `phase8-restore-20260924-b`.
- PostgreSQL: `phase8_restore_20260924_b_postgres`.
- ClickHouse: `phase8_restore_20260924_b_clickhouse`.
- MinIO buckets: `phase8-restore-20260924-b-imports`, `phase8-restore-20260924-b-models`, `phase8-restore-20260924-b-exports`, `phase8-restore-20260924-b-reports`, `phase8-restore-20260924-b-raw`, `phase8-restore-20260924-b-quarantine`, `phase8-restore-20260924-b-quality`, `phase8-restore-20260924-b-artifacts`.

The parent received these exact names after all store checks passed. Recovery did not restart writers or alter backend configuration. After handoff, the parent recreated only the task backend with the restored PostgreSQL and ClickHouse names using [compose.restore-readback.yml](../../artifacts/phase8-runtime-20260924/compose.restore-readback.yml). Worker and mlflow remain stopped. All restore-b databases and buckets are retained; no cleanup was performed.

## Restored application readback — parent PASS

The parent supplied [restore-api-readback.json](../../artifacts/phase8-runtime-20260924/restore-api-readback.json), inspected for this report update. It records status PASS, the exact restored database names above, and these successful readback checks:

- Incident GET preserves CLOSED status.
- Scenario and forecast IDs are preserved.
- Audit counts are preserved; the parent confirmed exactly one SIGNAL_ACKNOWLEDGED and one SCENARIO_CREATED audit.
- Analytics overview returns HTTP 200.

This is synthetic application readback against the restored PostgreSQL and ClickHouse stores. It supplements the earlier store verification; the original restore result JSON and its hash remain unchanged. MinIO object recovery is evidenced separately by the recovery runner's readback/hash checks. Independent read-only review of the source fixes and full root/backend regression were still running when the parent reported this result; this update makes no completion claim for them.

## Evidence and limits

Ignored evidence: `artifacts/phase8-runtime-20260924-restore/`.

- `FIXTURES_READY.json`, `preflight.json`, `operations.jsonl`: coordination and scoped execution.
- `backup-canonical/manifest.json`, `stores.json`, `postgres.dump`, `clickhouse/`, `minio/`: successful 31-artifact backup with verified coverage/hashes.
- `phase8-restore-20260924-b-result.json`, `restore-canonical.log`, `final-summary.json`: successful verification.
- `tdd-red.log`, `tdd-green.log`, `pg-roundtrip-red.log`, `pg-roundtrip-green.log`, `final-tests.log`: regression and final test evidence.
- `backup/`, `restore.log`, `pg-first-restore-inventory.json`: initial backup and detected mismatch.

Successful manifest SHA-256: `af2a672440c0661f4e1c178f76a1e1db0d8fb4de5bb4ea0cfb2cb589cb64a994`.
Result JSON SHA-256: `be234bf76abe487fb732262ba33964461fb1ab6b65544c2078e52057808ef796`.

This proves counts/constraints/revisions, ClickHouse aggregate totals and migration checksums, and object-byte recovery for the recorded fixtures. It is not an exhaustive hash of every PG/CH field. No shared cross-store snapshot exists: quiesced writers are required. The original recovery-script result retains application_workflow=NOT_TESTED because that script did not exercise the application; the separate parent evidence above records the subsequent restored-application readback PASS. rpo_rto_acceptance remains EXTERNAL_DEPENDENCY. Timing logs are diagnostic only; no actual RPO/RTO claim is made.
