# Pilot database recheck — 2026-09-24

Source: `codex/pilot-reproducibility`, `78d5f8c`.
Worktree: `C:/Users/zhasy/.codex/worktrees/medsignal-reproducibility/govtech_case1`.

Database migrations, all eight requested live integration tests, and automatic ClickHouse initialization using the unchanged production-default `medsignal_analytics` on fresh isolated storage **PASS**. The original hyphenated test-only database name **FAILS** because the vendor entrypoint does not quote identifiers. Its explicit recovery enabled parent API validation and is recorded separately from the successful default-name initialization proof. No product source or accepted schema files were changed.

## Results

All evidence below is under ignored `artifacts/phase8-runtime-20260924-db/`.

| Check | Result | Evidence |
| --- | --- | --- |
| Authenticated PostgreSQL and ClickHouse readiness | PASS | `readiness.log`: loopback SELECT 1 on both services |
| Main PostgreSQL empty-schema precondition | PASS | `clean-precondition.log`: zero public tables before migration |
| Clean PostgreSQL migration 0001–0008 | PASS | `pg-clean-upgrade.log`: all eight revisions applied, exit 0 |
| Main PostgreSQL drift check and repeat | PASS | `pg-phase8-runtime-20260924-check.log`, `-repeat.log`, `-revision.log`: no new operations; repeat exit 0; head `0008_mapping_versions` |
| New upgrade database at accepted 0006 | PASS | `created-phase8-runtime-upgrade-20260924.log`, `pg-legacy-0006.log`, `pg-legacy-revision.log` |
| Upgrade 0006–0008, drift check and repeat | PASS | `pg-legacy-to-head.log`, `pg-phase8-runtime-upgrade-20260924-check.log`, `-repeat.log`, `-revision.log`: head 0008, no drift, exit 0 |
| Fresh ClickHouse apply_all 001–006 and repeat | PASS | `ch-phase8-runtime-ch-clean-20260924.log`: six newly applied versions; repeat applied zero |
| Original test-only hyphenated ClickHouse automatic initialization | FAIL | `error-1790247992162192100.log`: UNKNOWN_DATABASE; `ch-init-container-complete.log`: startup SQL syntax error 62, followed by skipped initialization on restart |
| Explicit main ClickHouse recovery, apply_all and repeat | PASS | `ch-main-precondition.log`: database absent; `ch-phase8-runtime-20260924.log`: all six newly applied versions, repeat applied zero |
| Delivery PostgreSQL races | PASS | 3 tests in `integration-1790248127261037900.log` |
| ClickHouse publication, mapping scope and daily/fact equality | PASS | 1 test in the same integration log |
| Organization forecast PostgreSQL atomicity, retries and deduplication | PASS | 4 tests in the same integration log |
| Production-default ClickHouse automatic initialization on fresh isolated storage | PASS | `production-default-init-precondition.log`, `-resources.log`, `production-default-auto-init.log`, `production-default-init-container.log`: new project/volume; actual database `medsignal_analytics`; one table and one `001_init` row before migrations; zero restarts |
| Production-default ClickHouse migrations and repeat | PASS | `production-default-migrations.log`: six newly applied migrations, repeat zero; 14 tables and 7 ledger versions including `001_init` |
| Separate initialization-project cleanup | PASS | `production-default-init-cleanup.log`: no remaining project containers, networks or volumes |
| API, Keycloak, restore and production acceptance | NOT TESTED | Parent-owned work, outside this bounded database recheck |

Integration result: **8 passed**, no skips or failures, exit 0, 16.03 s. One Starlette/httpx deprecation warning was emitted. These are synthetic live-database checks. The PostgreSQL upgrade test establishes schema transition from a fresh 0006 database; it does not claim preservation of a populated legacy production dataset.

## Commands

From the worktree root, using the native virtual environment:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/run_db.py' ready
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/run_db.py' clean
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/run_db.py' checks
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/run_db.py' ch
# Original ch invocation: fresh-database PASS, then main-database UNKNOWN_DATABASE.
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/ch_main_recovery.py'
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/run_db.py' upgrade
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/run_db.py' checks phase8-runtime-upgrade-20260924
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/run_db.py' tests
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/inspect_ch_init.py'
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/reproduce_ch_init.py'
& '.venv/Scripts/python.exe' 'artifacts/phase8-runtime-20260924-db/verify_default_init.py'
```

The runner reads `ports.json` and `.env.phase8` internally; credentials are redacted from evidence. Recorded loopback ports: PostgreSQL 54455, ClickHouse HTTP 54456. The underlying commands are `python -m alembic upgrade head`, `python -m alembic check`, `python -m alembic upgrade 0006_scenario_analysis`, `apply_all(client, database/clickhouse/migrations)` twice per ClickHouse database, and:

```text
python -m pytest --no-showlocals --tb=short -ra tests/integration/test_delivery_postgres.py tests/integration/test_clickhouse_publication.py tests/integration/test_organization_forecast_atomicity.py
```

The clean, upgrade and recovery scripts deliberately reject unexpected pre-existing state. Do not rerun their creation steps against the parent's now-populated main database.

## Vendor identifier limitation and production-default initialization proof

Observed image: `clickhouse/clickhouse-server:24.8-alpine`; server reports 24.8.14.39. The isolated container has `CLICKHOUSE_DB=phase8-runtime-20260924`, the repository init-directory mount, and the task-owned `phase8-runtime-20260924_clickhouse-data` volume. This is not a missing Compose environment value (`ch-init-config.log`).

The captured image `/entrypoint.sh` uses the following SQL before processing init scripts (`ch-entrypoint.log`):

```text
CREATE DATABASE IF NOT EXISTS $CLICKHOUSE_DB
```

It does not quote the identifier. Startup logs show `create database 'phase8-runtime-20260924'`, followed by syntax error 62 at the first hyphen. The restarted entrypoint sees the database data directory and skips initialization, allowing the server to run without the configured database. Sending that exact unquoted SQL through the authenticated client reproduces the syntax error (`ch-init-unquoted-reproduction.log`); the parser rejects it without changing data.

`artifacts/phase8-runtime-20260924/prepare.py:10` assigns this hyphenated test-only name. The accepted product default `medsignal_analytics` is a valid unquoted identifier. No workaround embedding quote characters into `CLICKHOUSE_DB`, no schema change, and no vendor entrypoint change was made. The original hyphenated-name check remains FAIL as a test configuration/vendor identifier limitation.

A separate fresh Compose project, `phase8-runtime-init-20260924`, proved the actual production-default behavior. The database name was explicitly `medsignal_analytics`; physical isolation came from the project's separate server/container and new volume, not from its database name. The precondition confirmed no existing project containers, networks, volumes, or exact target volume. The successful run created:

- Container `3c27ae745584`, image `clickhouse/clickhouse-server:24.8-alpine`, image ID `sha256:b002e56ed5c16e224c312527f6fcba7e77216fec5d7a88a7828f59efc614feb5`.
- Volume `phase8-runtime-init-20260924_clickhouse-data`, created `2026-09-24T11:14:45Z`, with that exact Compose project label.
- Read-only repository `database/clickhouse` mount at `/docker-entrypoint-initdb.d`.
- Ephemeral host mapping `127.0.0.1:64518` to container HTTP 8123; existing random credentials loaded internally, never printed.

Before running migrations, authenticated access to `medsignal_analytics` succeeded, `SHOW TABLES` returned only `schema_migrations`, and that table contained exactly one `001_init` row. Container logs confirm automatic database creation and execution of `001_init.sql`; container `RestartCount` was zero. Then `apply_all` applied all six migrations, a repeat applied zero, and final inspection found 14 tables and seven ledger entries including `001_init`.

The accepted init SQL hardcodes `medsignal_analytics`, which matches the production default. It was not reached in the original hyphenated-name failure, because the vendor entrypoint failed first. The successful default-name proof used that file unchanged. Automatic init creates the database and initial ledger; the six application migrations were explicitly applied afterward.

The first fresh proof attempt hit a tuple-versus-list assertion in the ignored verification harness after connecting. Its resources were fully removed. Only that comparison was corrected; the successful rerun created fresh storage again. Initial evidence is retained as `initial-harness-production-default-*.log`. This was a harness failure, not evidence of a default-name database initialization failure.

After successful validation, `docker compose --project-name phase8-runtime-init-20260924 ... down --volumes` removed only the separate proof project. Post-cleanup inspection confirmed zero project containers, networks and volumes. This proof did not use or reuse the parent's database server/volume and did not purge its synthetic fixtures.

## Isolation and handoff

On the parent runtime server, only the authorized phase8 PostgreSQL databases (`phase8-runtime-20260924`, `phase8-runtime-upgrade-20260924`, `phase8-runtime-tests-20260924`) and task ClickHouse databases were mutated. ClickHouse integration tests create/drop only their own UUID-named `phase8-d-*` databases. PostgreSQL tests create/drop only their own UUID-named schemas in the separate test database. The ClickHouse `default` database was used only as an administrative connection context. The additional explicitly authorized production-default initialization proof used `medsignal_analytics` inside its physically separate `phase8-runtime-init-20260924` server and volume, then removed only that proof project.

The parent was notified immediately after recovery established main PostgreSQL head and main ClickHouse readiness, and again with the confirmed initialization cause and all integration results. Subsequent investigation read container configuration/logs and reproduced invalid SQL; it did not delete parent fixtures. No application source, PostgreSQL 0001–0006, ClickHouse 001–005, models or repositories were changed. No commits, pushes, subagents, real-data reads, or container restarts were performed. Volume cleanup was limited to the separately authorized initialization-proof project; no other project was changed.
