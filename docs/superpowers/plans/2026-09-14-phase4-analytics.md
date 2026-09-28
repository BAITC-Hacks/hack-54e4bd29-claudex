# PHASE 4 Analytics & Situation Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить безопасную описательную аналитику и Ситуационный центр поверх фактов Phase 3B.

**Architecture:** FastAPI вызывает framework-free `AnalyticsService`; сервис применяет permission/scope, централизованные определения метрик и cache policy, а ClickHouse SQL находится в `SqlAnalyticsRepository`. PostgreSQL предоставляет watermark и quality metadata через существующий Unit of Work.

**Tech Stack:** FastAPI, Pydantic, ClickHouse, PostgreSQL, Redis, Next.js, TypeScript, TanStack Query, Apache ECharts, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-14-phase4-analytics-design.md`

## Global Constraints

- Не реализовывать ML, прогнозирование, Risk Score, Signal Engine, What-if или LLM.
- Не рассчитывать bed occupancy/load percentage и не показывать неподтверждённую долю отказов.
- Waiting — один поставленный срез; `registration_dt` не является историей snapshots.
- Treated — snapshot без подтверждённого reporting period.
- Несопоставленные source organizations доступны только `ADMIN` и `HEALTH_AUTHORITY`.
- `ANALYTICS_MIN_CELL_SIZE` по умолчанию равен 10.
- Ни event-level данные, ни чувствительные идентификаторы не выдаются API.
- Кэш-ключ включает filters, scope и completed-import watermark.

---

### Task 1: Pure analytics contracts and metric registry

**Files:**
- Create: `backend/app/business/analytics/contracts.py`
- Create: `backend/app/business/analytics/metrics.py`
- Create: `backend/app/business/analytics/privacy.py`
- Create: `backend/tests/unit/test_analytics_metrics.py`

**Interfaces:**
- Produces `AnalyticsFilter`, `Granularity`, result dataclasses, `MetricDefinition`, `METRIC_REGISTRY`, `suppress_small_cells`.

- [ ] Write failing tests for metric identities, date-range limits, referral status, waiting-duration exclusion and cell suppression.
- [ ] Run the test module and confirm failures are caused by missing behavior.
- [ ] Implement pure types and formulas without FastAPI, SQLAlchemy or ClickHouse imports.
- [ ] Run the test module and refactor while green.

### Task 2: Scope-aware ClickHouse repository and metadata ports

**Files:**
- Create: `backend/app/business/analytics/ports.py`
- Create: `backend/app/repositories/clickhouse_analytics.py`
- Modify: `backend/app/business/ports.py`
- Modify: `backend/app/repositories/analytics.py`
- Modify: `backend/app/repositories/directory.py`
- Modify: `backend/app/repositories/unit_of_work.py`
- Modify: `backend/tests/fakes.py`
- Create: `backend/tests/unit/test_analytics_repository_contract.py`

**Interfaces:**
- Consumes pure contracts from Task 1.
- Produces aggregate repository methods for overview, timeseries, waiting age, observed waiting, organizations, treated snapshot and freshness.

- [ ] Write failing contract tests using a recording ClickHouse client and literal expected query parameters.
- [ ] Verify tests fail before repository implementation.
- [ ] Implement parameterized, bounded aggregate queries and source organization reference handling.
- [ ] Add PostgreSQL queries for latest completed imports, quality summaries and regional hospital IDs.
- [ ] Run focused tests.

### Task 3: Analytics service, authorization and scoped cache

**Files:**
- Create: `backend/app/business/analytics/service.py`
- Create: `backend/app/business/analytics/cache.py`
- Create: `backend/app/adapters/analytics_cache.py`
- Modify: `backend/app/security/permissions.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/metrics.py`
- Modify: `backend/app/composition.py`
- Create: `backend/tests/unit/test_analytics_service.py`
- Modify: `backend/tests/unit/test_config.py`

**Interfaces:**
- Consumes `AnalyticsRepository`, UoW metadata and `SecurityContext`.
- Produces service methods used only by API routes.

- [ ] Write failing tests for permissions, regional/hospital scope, unmapped visibility, cache scope isolation, watermark invalidation and Redis fail-open.
- [ ] Verify expected failures.
- [ ] Implement service orchestration and short-TTL cache adapter.
- [ ] Add low-cardinality Prometheus counters/histogram.
- [ ] Run focused tests.

### Task 4: Versioned analytics API

**Files:**
- Create: `backend/app/schemas/analytics.py`
- Create: `backend/app/api/v1/analytics.py`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/tests/integration/test_analytics_api.py`

**Interfaces:**
- Consumes AnalyticsService response dataclasses.
- Produces `/api/v1/analytics/*` JSON contracts.

- [ ] Write failing API tests for auth, filters, oversized ranges, arbitrary values, 404 source references and response metadata.
- [ ] Verify failures.
- [ ] Implement strict Pydantic query/response schemas and thin routes.
- [ ] Run API tests and backend architecture checks.

### Task 5: Situation Center frontend contracts and reusable states

**Files:**
- Create: `frontend/src/features/analytics/types.ts`
- Create: `frontend/src/features/analytics/api.ts`
- Create: `frontend/src/features/analytics/hooks.ts`
- Create: `frontend/src/features/analytics/components/*.tsx`
- Add: Apache ECharts dependency.
- Create: `frontend/src/__tests__/analytics-components.test.tsx`

**Interfaces:**
- Produces runtime-validated API client calls, TanStack Query hooks and accessible components.

- [ ] Write failing tests for loading, empty, partial, error, quality warning and suppressed values.
- [ ] Verify failures.
- [ ] Implement components, including chart table alternative.
- [ ] Run component tests, lint and typecheck.

### Task 6: Dashboard and organization pages

**Files:**
- Create: `frontend/src/app/dashboard/page.tsx`
- Create: `frontend/src/app/hospitals/[id]/page.tsx`
- Create: `frontend/src/app/organizations/[ref]/page.tsx`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/components/site-header.tsx`
- Create: `frontend/src/__tests__/situation-center.test.tsx`

**Interfaces:**
- Consumes Task 5 hooks/components.
- Produces reviewable Phase 4 routes with no client-side business formulas.

- [ ] Write failing page tests for success, degraded dependencies and explicit snapshot/mapping labels.
- [ ] Verify failures.
- [ ] Implement the Situation Center and both identity-space detail pages.
- [ ] Run frontend tests and production build.

### Task 7: Documentation and architecture enforcement

**Files:**
- Create: `docs/analytics/ANALYTICS_ARCHITECTURE.md`
- Create: `docs/analytics/METRIC_DEFINITIONS.md`
- Create: `docs/analytics/WAITING_SEMANTICS.md`
- Create: `docs/analytics/PRIVACY.md`
- Create: `docs/analytics/CACHE_STRATEGY.md`
- Create: `docs/analytics/SITUATION_CENTER.md`
- Modify: `docs/API.md`
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

- [ ] Document every formula, limitation, scope rule and failure mode.
- [ ] Add configuration without insecure defaults or claims of operational SLA.
- [ ] Run docs link/architecture checks available in the repository.

### Task 8: Real-data integration and performance validation

**Files:**
- Create: `backend/tests/integration/test_clickhouse_analytics.py`
- Create: `scripts/validate-phase4.py`
- Modify: `Makefile`

- [ ] Write aggregate consistency tests (`sum(daily) == count(facts)`) and verify they fail before the integration fixture exists.
- [ ] Implement a read-only validation command that outputs only aggregates and latency.
- [ ] Run full backend, pipeline, security, architecture and frontend suites.
- [ ] Run real-data validation twice to record cold/warm cache latency and hit/miss behavior.
- [ ] Inspect `/dashboard`, `/hospitals/[id]` and `/organizations/[ref]` without exposing event-level records.

