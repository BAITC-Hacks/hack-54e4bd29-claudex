# Runtime acceptance recheck — 2026-09-24

Source baseline: `78d5f8c`, branch `codex/pilot-reproducibility`. This extends the September23 consolidation report. It does not admit an operational model or certify production TLS/SSO.

## Isolation and recovery of the local Docker runtime

The initial Engine29.2.1 could list existing containers and execute pg_isready but could not create a new network or start the task project. The user explicitly authorized restarting Docker Desktop. No Docker volume/image pruning, source dataset alteration or destructive Git operation occurred.

After a failed startup, host logs identified an inaccessible zero-byte `Docker/run/dockerInference` IPC reparse point. Windows refused deletion. With Desktop stopped, its runtime directory (verified to contain only that socket) was preserved as `run-phase8-stale-20260924`; no application data was removed. After the user's interruption/resumption, Engine29.8.0 was available. This task did not install an Engine update and does not attribute recovery solely to the socket operation. All ten pre-existing MedSignal services returned, seven with healthy checks.

The new `phase8-runtime-20260924` Compose project created fresh named volumes and separate networks. Published test ports bind only127.0.0.1. Random ephemeral credentials/realm files are Git-ignored and never printed. The HTTP development realm is not corporate SSO or production TLS evidence.

## Verified gates

| Check | Status | Evidence / boundary |
|---|---|---|
| New isolated storage/project creation | PASS | New PG/CH/Redis/MinIO volumes and edge/data networks; existing volumes preserved |
| PostgreSQL clean0001–0008 and0006→0008 | PASS | Real new databases, both drift checks and idempotent repeats; upgrade baseline was empty0006, not populated production |
| ClickHouse001–006 / repeated migration | PASS | Fresh analytical DB, repeat applied zero |
| Default ClickHouse automatic initialization | PASS | Separate fresh `phase8-runtime-init-20260924` project with actual production-default DB `medsignal_analytics`, zero restarts; see database report |
| Hyphenated test DB auto-init | FAIL | Vendor24.8 entrypoint uses unquoted identifier. Manually recovered only task DB; production default initialization separately verified |
| Live DB concurrency/publication/aggregation | PASS |8 tests:3delivery races,1CH mapping/publication/daily-total check,4forecast atomicity/idempotency checks |
| `/api/v1/health` and `/ready` | PASS |200 through isolated runtime; required PG/CH/Redis reachable |
| Celery worker ping | PASS | One isolated worker returned pong; uses existing dependency image and current development source mounts |
| Real signed Keycloak identities | PASS | Six synthetic identities cover allfive roles plus scoped HEALTH_AUTHORITY; authentication, hospitalIDOR, scopes, global forecast/signal denial and invalid bearer tested |
| Human workflow with actual API/PG | PASS | Two actors acknowledge sameversion:200/409; Incident create/assign/close; OBSERVED Scenario preview/save/retry; exactly one corresponding acknowledge and scenario audit |
| Backend process restart and state persistence | PASS | After actual isolated backend restart, saved Incident remainedCLOSED and ScenarioID/audit counts unchanged |
| Request ID and sensitive-header logs | PASS | Custom requestID echoed/logged; synthetic auth/cookie canary and actual test access token absent from backend/nginx/worker logs |
| Node22 production frontend + monitoring container | PASS | Production HTTP/asset/route smoke;88synthetic monitoring tests in Pythoncontainer; see container report |
| Production backend stage and non-root | PASS | Fresh production stage build; actual UID1001 with networkdisabled/read-only filesystem |
| Actual cross-store restore | PASS | New PG/CH databases and eight MinIO buckets restored; PG25tables/89constraints/revision, CH30facts/6migration checksums, object readback hashes match. Synthetic only; see recovery report |
| Restored application readback | PASS | Backend pointed only at restored PG/CH: saved IncidentCLOSED, same Scenario/Forecast IDs, one acknowledgement and scenario audit, overview200 |
| Source regression after runtime corrections | PASS | Backend611passed/2skipped; root+ML334passed/2skipped; frontend79passed; lint/typecheck/mypy and12architecture contracts pass. Skips and separate opt-in runs below |
| Hosted CI execution | NOT TESTED | Local equivalent checks do not establish a GitHub Actions run |
| Existing-deployment real-data benchmark acceptance | FAIL |20concurrent/200requests per endpoint: errors on every route. Existing main only, cacheUNCONTROLLED; see performance report |
| New-branch real-data benchmark | NOT TESTED | Real dataset remains in existing main deployment; no approved new delivery contract fabricated to load task stack |
| Frontend image security recheck | PASS | OpenSSL3.5.7-r0→3.5.8-r0 within same Alpine branch; pinned Trivy0.58.2 independent unfiltered rescan returned0findings |
| Backend image vulnerabilities / release risk acceptance | FAIL |52HIGH package findings,12distinct CVEs,0CRITICAL, no reported fixed versions. No suppression or risk approval inferred |
| Full unattended production deployment | NOT TESTED | This test used local realm, loopback ports, separate migration proofs and explicit task DB recovery; not a turnkey production deployment assertion |
| Production TLS/SSO/perimeter/RPO-RTO | EXTERNAL DEPENDENCY | Real infrastructure and owner decisions not supplied |
| Approved data/mappings/independent M3/model release | EXTERNAL DEPENDENCY | No operational model enabled; no real training or imports performed |

## Test data and actual data boundary

Live write tests use deliberately synthetic data: two regions, three hospitals, six identities,30referral facts, one saved synthetic forecast and one GLOBAL workflow Signal (plus development domain fixtures). These verify persistence/authorization and do not demonstrate predictive quality. The source writers were stopped before recovery verification.

A separate read-only query against existing imported facts succeeded with bounded execution: referrals767130, waiting765182, refusals1508732, treated snapshot2196. No patient-level row/sample or raw source file was read. A performance baseline against that existing deployment must identify its older source/image revision; it is not new-branch acceptance.

## Commands and detailed evidence

All operations ran in the isolated reproducibility worktree. Generated secrets and raw command logs remain under ignored `artifacts/phase8-runtime-20260924*`. Repository test code and detailed commands are linked below.

```text
python -m alembic upgrade head
python -m alembic check
python -m alembic upgrade 0006_scenario_analysis  # separate new upgrade DB only
python -m pytest --no-showlocals --tb=short -ra tests/integration/test_delivery_postgres.py tests/integration/test_clickhouse_publication.py tests/integration/test_organization_forecast_atomicity.py
python -m pytest tests/security/test_real_keycloak_roles.py -q --no-showlocals --tb=short
python -m scripts.phase8_e2e --base-url http://127.0.0.1:54454 --output artifacts/phase8-runtime-20260924/workflow-evidence.json
docker build --target production --tag phase8-runtime-20260924-backend:production backend
docker run --rm --name phase8-runtime-20260924-backend-uid --network none --read-only --entrypoint id phase8-runtime-20260924-backend:production -u
```

The DB test DSNs and acceptance identities came only from process environment. Do not rerun clean creation steps against now-populated fixture databases. `workflow-evidence.json` was extended by an actual restart/readback check; the generic harness correctly defaults that field to NOT TESTED.

- [Database and automatic-init recheck](PILOT_DATABASE_RECHECK.md)
- [Container builds and smoke](PILOT_CONTAINER_RECHECK.md)
- [Restore and application readback](PILOT_RESTORE_RECHECK.md)
- [Previous source consolidation report](PILOT_CONSOLIDATION_IMPLEMENTATION.md)
- [Performance evidence](../analytics/PERFORMANCE_RECHECK.md)

## Runtime fixes and regression

Three narrowly scoped fixes were made after failures were reproduced:

1. Restore accepts strictly allowlisted quoted ClickHouse database names containing hyphens; table names remain separately constrained. Injection/traversal/whitespace inputs remain rejected before writes.
2. PostgreSQL CHECK definitions are reparsed by PostgreSQL on empty transaction-local temporary tables before inventory comparison. This preserves casts, names and validation flags while avoiding false mismatches from pg_dump's equivalent array-cast rendering. A real dump/restore regression passes; changing the allowed status set still fails verification.
3. Frontend production stage applies security patches from its existing Alpine repositories. No auth, base major version, dependency validation or scanner policy was weakened.

Final backend run used isolated D/R1 PostgreSQL DSNs and ClickHouse connections: **611passed,2skipped** in75.80s. Skips are the two tests hardcoding real Phase3B counts; the isolated fixtures intentionally do not contain those real records. All eight live publication/concurrency tests ran in this suite. Root security/pipeline/audit/operations/ML: **334passed,2skipped** in54.21s; opt-in real-token and PGroundtrip were separately executed successfully (six identities in one test; operations full live suite40passed). Existing dependency deprecation/test-key warnings remain, without hidden failures.

Frontend lint/typecheck and **79tests/10files** pass; production Node22 image rebuild and HTTP/SSR checks pass separately. Backend Ruff check/format226files, mypy159files, operations Ruff7files and import-linter12kept/0broken pass. Basic source/history secret scan has zero findings. Independent review of the five changed source/test files found no actionable findings (29passed/1live-test skipped in reviewer run; live roundtrip independently executed by recovery worker).

Additional commands executed:

```text
python artifacts/phase8-runtime-20260924-db/run_db.py tests tests
python -m pytest tests ml/tests -q --no-showlocals --tb=short
python -m ruff check scripts/operations tests/operations
python -m ruff format --check scripts/operations tests/operations
lint-imports --config .importlinter
python scripts/security/scan_secrets.py --history
# cwd backend
python -m ruff check .
python -m ruff format --check .
python -m mypy app
# cwd frontend
npm run lint
npm run typecheck
npm test
# ignored task helper; secrets never printed
python artifacts/phase8-runtime-20260924/verify_restore_api.py
```

## Backend scanner findings

Pinned scanner `aquasec/trivy:0.58.2`, production backend stage, Debian13.7. Counts below are package-level reports, not unique exploit paths. Fixed versions were absent in the scanner database at this run; no risk waiver is implied.

| Vulnerability | Affected package reports | Severity |
|---|---:|---|
| CVE-2025-69720 | 4 | HIGH |
| CVE-2026-12064 | 2 | HIGH |
| CVE-2026-16742 | 2 | HIGH |
| CVE-2026-54369 | 1 | HIGH |
| CVE-2026-76642 | 9 | HIGH |
| CVE-2026-78408 | 9 | HIGH |
| CVE-2026-78409 | 9 | HIGH |
| CVE-2026-78410 | 9 | HIGH |
| CVE-2026-8286 | 2 | HIGH |
| CVE-2026-8458 | 2 | HIGH |
| CVE-2026-8927 | 2 | HIGH |
| CVE-2026-9538 | 1 | HIGH |

After restored backend and patched frontend recreation, `/health`, `/ready` and `/monitor` returned200, excluded `/api/pilot/health` returned404. The real-role test repeated against restored PostgreSQL passed (1test, six identities,1.96s). Evidence: `final-http-smoke.json`, `restored-role-tests.log`. Accepted PG0001–0006 and CH001–005 remain unchanged versus `d965aff`.

## Remaining gates and resource disposition

**Operational release remains NOT ADMITTED.** The pinned scanner found backend OS-package issues with no fixed version reported. These are not automatically accepted false positives. Track upstream fixes and obtain an explicit security-owner decision for the exact image before release; do not suppress findings to pass CI. The frontend fix and zero-findings rescan do not clear backend risk.

The old main deployment benchmark is a diagnostic baseline: overview12.5%, referrals6.5%, refusals3%, organizations12% request failures at concurrency20. Mixed-status p95 values are454/808/811/5070ms, respectively. They are not successful-request SLA evidence. Investigate gateway limiting versus backend failures with request-correlated traces, profile organization queries, then repeat on the actual candidate revision with controlled cache and approved data. Do not weaken rate limits to hide failures.

New source admission/M3, approved mapping/delivery contracts, corporateSSO, realTLS/perimeter and operational alert exercises remain open as recorded in the release register. Recovery proves recorded synthetic content; no full PG/CH field hashing, atomic cross-store snapshot or actual RPO/RTO acceptance is claimed.

No current application volumes or raw datasets were removed. Task backup/restore targets and ignored evidence are retained for review. The isolated backend now uses restored-b PG/CH databases through `compose.restore-readback.yml`; object buckets were verified by the recovery tool, not application object APIs. Isolated worker/mlflow remain stopped; the task frontend was recreated with the patched production image. Temporary smoke/scanner/default-init containers were cleaned only within their owned namespaces. Ten pre-existing MedSignal services were preserved after the authorized Desktop recovery. Do not use this temporary HTTP fixture stack as production.
