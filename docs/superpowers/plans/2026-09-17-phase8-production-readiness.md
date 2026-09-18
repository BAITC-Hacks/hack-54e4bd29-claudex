# Phase 8 Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the accepted MedSignal Phase 0–7 system reproducibly deployable, recoverable, security-reviewed, performance-measured and demonstrable without adding product features.

**Architecture:** Preserve the modular monolith and existing Compose stack. Add an incremental production overlay, one-shot analytical migrations, isolated operational verification tooling and evidence documents. All mutations occur in `phase8-*` resources; source datasets remain read-only.

**Tech Stack:** Docker Compose, FastAPI/Pydantic/SQLAlchemy/Alembic, PostgreSQL, ClickHouse, Redis, MinIO, Keycloak, Nginx, Next.js, pytest/Vitest, Prometheus client, Trivy.

**Spec:** `docs/superpowers/specs/2026-09-17-phase8-production-readiness-design.md`

## Global Constraints

- Do not modify accepted PostgreSQL migrations `0001–0006`.
- Do not create `0007` solely to resolve ORM metadata drift.
- Preserve `docker compose up` as the local/demo workflow.
- Use only `phase8-*` names for temporary databases, buckets, volumes and projects.
- Never mutate `C:\Users\zhasy\Downloads\data`; mount it read-only.
- Do not delete current volumes or imported facts.
- Corporate SSO, real TLS/DNS/firewall/VPN are external dependencies until actually configured.
- PASS requires executed evidence; documentation alone is not PASS.

---

### Task 1: Repair the accepted baseline and Alembic metadata

**Files:**
- Modify: `backend/seeds/dev_seed.py`
- Modify: `backend/app/models/data_import.py`
- Modify: `backend/app/models/quality.py`
- Modify: `backend/app/models/mapping.py`
- Modify: `backend/app/models/analytics.py`
- Modify: `.github/workflows/ci.yml`
- Test: `backend/tests/unit/test_schema_metadata.py`

**Interfaces:**
- Produces ORM metadata exactly matching migrations `0001–0006`.
- Produces a CI `alembic check` against a migrated PostgreSQL service.

- [ ] Write metadata assertions for `BIGINT`, server defaults and Forecast indexes.
- [ ] Run the assertions and confirm failure against stale ORM metadata.
- [ ] Align ORM types/defaults/indexes without changing accepted migrations.
- [ ] Fix the single seed formatting defect.
- [ ] Verify tests, Ruff, format and `alembic check` on current and fresh databases.

### Task 2: Make clean Compose projects reproducible

**Files:**
- Modify: `docker-compose.yml`
- Create: `docker-compose.production.yml`
- Modify: `data_pipeline/loading/clickhouse_migrations.py`
- Modify: `Makefile`
- Test: `tests/security/test_compose_contract.py`

**Interfaces:**
- Produces one-shot `clickhouse-migrate` and project-scoped container names.
- Production overlay selects production image stages and removes development mounts.

- [ ] Write Compose contract tests for no explicit container names, private stores, production targets and migration dependencies.
- [ ] Confirm tests fail on current Compose.
- [ ] Remove explicit container names and add idempotent ClickHouse migration service.
- [ ] Add production overlay without duplicating the stack.
- [ ] Verify local Compose, production merged config and two isolated project configs.

### Task 3: Enforce production configuration and identity contracts

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `infrastructure/keycloak/realm-medsignal-dev.json`
- Modify: `backend/seeds/dev_seed.py`
- Create: `infrastructure/keycloak/realm-production-contract.md`
- Test: `backend/tests/unit/test_config.py`
- Test: `tests/security/test_real_keycloak_roles.py`

**Interfaces:**
- Produces fail-fast non-local configuration validation.
- Produces synthetic dev identities whose Keycloak subjects match PostgreSQL scopes.

- [ ] Add failing tests for trusted hosts, HTTPS boundary and local-only realm restrictions.
- [ ] Implement minimal validation and environment classification.
- [ ] Add deterministic HEALTH_AUTHORITY/REGION/HOSPITAL demo identities.
- [ ] Obtain real tokens and test role mapping, GLOBAL/REGION/HOSPITAL IDOR paths.
- [ ] Record corporate SSO as external dependency.

### Task 4: Add practical backup and verified restore

**Files:**
- Create: `scripts/operations/backup.py`
- Create: `scripts/operations/restore_verify.py`
- Create: `scripts/operations/common.py`
- Modify: `Makefile`
- Modify: `.gitignore`
- Test: `tests/operations/test_backup_contract.py`

**Interfaces:**
- `backup.py --output <dir>` creates PostgreSQL, ClickHouse and MinIO artifacts plus manifest.
- `restore_verify.py --backup <dir> --namespace phase8-*` restores only into isolated targets and returns JSON evidence.

- [ ] Write failing command/manifest/path-boundary tests.
- [ ] Implement PostgreSQL dump and isolated restore verification.
- [ ] Implement ClickHouse table export and isolated database restore verification.
- [ ] Implement MinIO mirror and isolated bucket restore verification.
- [ ] Verify representative operational entities, fact counts and artifact checksums.
- [ ] Document Redis as non-authoritative and excluded.

### Task 5: Fill focused observability gaps

**Files:**
- Create: `backend/app/core/http_metrics.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/workers/tasks.py`
- Modify: `infrastructure/nginx/conf.d/default.conf`
- Test: `backend/tests/unit/test_http_metrics.py`

**Interfaces:**
- Produces low-cardinality request and job outcome metrics.
- Keeps `/metrics` private at nginx.

- [ ] Add failing tests for normalized route labels and request latency/error metrics.
- [ ] Implement middleware metrics without user/patient/high-cardinality labels.
- [ ] Add Signal/forecast/import operation outcome metrics where missing.
- [ ] Verify public `/metrics` remains 404 and internal metrics are readable.

### Task 6: Add security and privacy acceptance tooling

**Files:**
- Create: `scripts/security/scan-secrets.py`
- Create: `scripts/security/scan-images.ps1`
- Create: `tests/security/test_application_boundaries.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Secret scan reports paths/rules but never matched values.
- Image scan records pinned Trivy version, image digest and severity counts.

- [ ] Add failing tests for secret value redaction and disallowed tracked files.
- [ ] Implement repository/history secret scanning.
- [ ] Add representative IDOR, mass-assignment, filter/path and error-leakage tests.
- [ ] Scan backend/frontend/nginx images using pinned Trivy.
- [ ] Recheck privacy-at-rest after real import.

### Task 7: Build E2E, demo and safe reset workflows

**Files:**
- Create: `scripts/phase8-e2e.py`
- Create: `scripts/demo/prepare.py`
- Create: `scripts/demo/reset.py`
- Create: `tests/e2e/test_phase8_contract.py`
- Modify: `Makefile`

**Interfaces:**
- E2E uses real Keycloak tokens and backend APIs.
- Demo manifest records only Phase 8-created operational IDs.
- Reset refuses non-`phase8-` namespace and never touches analytical facts.

- [ ] Write failing namespace and manifest-boundary tests.
- [ ] Implement authenticated analytics→forecast→signal→scenario→incident→audit flow.
- [ ] Implement isolated demo preparation and reset.
- [ ] Verify reset preserves imported ClickHouse row counts and source fingerprints.

### Task 8: Measure real-data performance

**Files:**
- Create: `scripts/performance/benchmark.py`
- Create: `scripts/performance/background_jobs.py`
- Create: `tests/performance/test_benchmark_statistics.py`

**Interfaces:**
- Benchmark JSON includes endpoint, concurrency, requests, errors, p50/p95/p99, cache state and dataset counts.
- Background report separates import, Signal Engine and forecast duration.

- [ ] Write failing percentile/report-contract tests.
- [ ] Implement bounded async HTTP benchmark with 20 concurrent users.
- [ ] Clean-deploy an isolated Compose project and apply all migrations.
- [ ] Import only allowlisted core data from the read-only source.
- [ ] Run benchmark and background measurements on real facts.

### Task 9: Produce operational documentation and acceptance evidence

**Files:**
- Create: `docs/runbooks/OPERATOR.md`
- Create: `docs/runbooks/ADMINISTRATOR.md`
- Create: `docs/runbooks/BACKUP_RESTORE.md`
- Create: `docs/runbooks/DEMO.md`
- Create: `docs/PHASE_8_ACCEPTANCE.md`
- Create: `docs/GOVTECH_TRACEABILITY.md`
- Create: `docs/PRESENTATION_METRICS.md`
- Modify: `README.md`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/TESTING.md`

**Interfaces:**
- Acceptance uses only PASS/FAIL/NOT TESTED/EXTERNAL DEPENDENCY/NOT APPLICABLE.
- Presentation metrics are copied only from generated verification evidence.

- [ ] Document exact operator and administrator commands.
- [ ] Document local/demo versus production boundaries and external controls.
- [ ] Map GovTech requirements to implementation, evidence and limitations.
- [ ] Generate acceptance and presentation facts from executed checks.
- [ ] Link concise runbooks from README.

### Task 10: Run the complete final gate

**Files:**
- Modify only evidence documents when results change.

**Interfaces:**
- Produces final verified Phase 8 readiness matrix and exact reproduction commands.

- [ ] Run all backend, pipeline, audit, ML and frontend tests.
- [ ] Run Ruff, format, mypy, import-linter, ESLint, TypeScript and production build.
- [ ] Run Compose validation, current/fresh Alembic check and clean deployment.
- [ ] Run real-token RBAC/IDOR, secrets, image, privacy and network checks.
- [ ] Run backup/restore for all three persistent stores.
- [ ] Run real-data performance, background jobs, E2E and demo reset.
- [ ] Run `git diff --check` and record the exact Git state.
- [ ] Mark every acceptance row strictly from observed evidence.
