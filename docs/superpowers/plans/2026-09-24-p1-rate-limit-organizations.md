# P1 Rate Limiting and Organization Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the existing P1 branch with a correct 429 contract and a faster, scope-safe organization list/detail.

**Architecture:** Keep FastAPI service/repository boundaries. Nginx handles edge throttling. PostgreSQL supplies names in a batch. ClickHouse serves organization aggregates from a publication-aware per-import rollup; Redis caches only fully scoped results.

**Tech Stack:** Nginx, FastAPI, SQLAlchemy, ClickHouse 24.8, Redis, pytest, Docker Compose.

**Spec:** User request attached in this task, sections 2–3 and 16–19.

## Global Constraints

- Preserve the existing `page/page_size` API and source/canonical identity namespaces.
- Only PostgreSQL-published import IDs and a verified mapping version may authorize analytical reads.
- No personal identifiers, raw medical rows, secrets, or tokens in cache keys, logs, or artifacts.
- Do not merge or push to `main`.

## Review Focus

- A throttled API call must return JSON 429, Retry-After and the same request ID in header/body.
- An empty organization page after a large offset must still report the correct total.
- A failed or partial import must never contribute to cached or uncached organization results.
- A revoked hospital mapping must not be reused from a previous cache entry.
- A source reference must resolve in its exact source namespace without enumerating 20,000 organizations.

---

### Task 1: Existing branch and baseline repair

**Files:** `backend/app/repositories/analytics_metadata.py`, `backend/tests/unit/test_analytics_metadata_repository.py`, `backend/app/adapters/composition.py`, `backend/tests/unit/test_import_service.py`.

- [ ] Verify existing branch tests and run baseline checks with writable test/cache directories.
- [ ] Add a repository test proving one SQL query for several canonical names and no query for empty input.
- [ ] Fix formatting/lint in the existing PR and resolve the two pre-existing mypy protocol errors without weakening the contracts.
- [ ] Re-run backend pytest, ruff, mypy and import-linter; commit the repair.

### Task 2: Edge rate limit contract

**Files:** `infrastructure/nginx/conf.d/default.conf`, `infrastructure/nginx/nginx.conf`, `tests/security/test_nginx_rate_limit.py`, `docs/API.md`, `docs/SECURITY.md`.

- [ ] Write a failing integration/contract test for 429, Retry-After, JSON error and request ID.
- [ ] Verify the Nginx configuration under Compose, including auth/import/API/analytics locations and limit zones.
- [ ] Make the minimal config correction, document current analytical policy and trusted proxy requirements.
- [ ] Run the test and Nginx config check; commit.

### Task 3: Direct source organization detail

**Files:** `backend/app/repositories/clickhouse_analytics.py`, `backend/tests/unit/test_clickhouse_analytics_repository.py`.

- [ ] Add a failing test that forbids calling `organizations(limit=20000)` for source detail.
- [ ] Add an exact digest predicate within the known identity namespace and a bounded query.
- [ ] Verify 404, scope and mapping semantics against synthetic ClickHouse fixtures; commit.

### Task 4: Publication-aware organization rollup

**Files:** `database/clickhouse/migrations/006_organization_daily.sql`, `backend/app/repositories/clickhouse_analytics.py`, `backend/tests/integration/test_clickhouse_analytics.py`, `docs/analytics/ANALYTICS_ARCHITECTURE.md`.

- [ ] Write a failing integration test showing facts, published rollup and filtered totals match with a failed import excluded.
- [ ] Add a per-import daily aggregate with exact source namespace, source key, profile, date and aggregate states for waiting-duration median; do not use a mapping ID as immutable source truth.
- [ ] Backfill existing fact imports reproducibly and make new imports populate the rollup; preserve publication gating.
- [ ] Change list queries to use the rollup and retain page/page_size behavior; verify totals and scopes; commit.

### Task 5: Scoped cache and benchmark

**Files:** `backend/app/business/analytics/ports.py`, `backend/app/business/analytics/service.py`, `backend/app/repositories/redis_cache.py` (or existing cache adapter), tests, `docs/analytics/CACHE_STRATEGY.md`.

- [ ] Write a failing test for cache isolation by scope, filters, page, mapping generation and import watermark.
- [ ] Add short TTL organizations cache; reject an entry if publication changes before response.
- [ ] Run before/after benchmark at the same data size and concurrency, separating 429 from application errors.
- [ ] Run full required checks, review diff/secrets/migrations and commit documentation/results.
