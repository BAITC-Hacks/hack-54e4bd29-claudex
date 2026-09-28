# Phase 7 Scenario Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver secure, immutable, provenance-bearing referral inflow scenario analysis from observed analytics or persisted forecasts.

**Architecture:** FastAPI routes call a framework-free `ScenarioService`; it resolves authoritative baselines through existing analytics and forecast ports and persists Scenario plus AuditEvent through the existing Unit of Work. PostgreSQL stores immutable scenario history; Next.js renders preview/save flows without performing authoritative calculations.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, pytest, Next.js, TypeScript, TanStack Query, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-17-phase7-scenario-analysis-design.md`

## Global Constraints

- Only `REFERRAL_INFLOW_CHANGE` and assumptions `-0.20`, `-0.10`, `0.10`, `0.20`.
- `Decimal`, `ROUND_HALF_UP`, four decimal places.
- `Forecast.status` validity and `CURRENT`/`STALE` freshness are separate fields.
- Preview never persists or audits; save always reacquires and recalculates.
- Saved scenarios are immutable and retry-idempotent by `(created_by, client_request_id)`.
- Do not add Celery, ML, capacity, overload, recommendation, patient-level, or fuzzy-mapping behavior.

---

### Task 1: Domain calculation and contracts

**Files:**
- Create: `backend/app/business/simulation/contracts.py`
- Create: `backend/app/business/simulation/calculation.py`
- Test: `backend/tests/unit/test_scenario_calculation.py`

**Interfaces:**
- Produces `ScenarioBaselineRequest`, `ScenarioPreview`, `calculate_referral_inflow_change()` and strict assumption validation.

- [ ] Write failing tests for four assumptions, half-up rounding, unsupported `0.15`, invalid periods, and separated forecast validity/freshness.
- [ ] Run the focused tests and confirm failures are due to missing contracts.
- [ ] Implement the smallest Decimal calculation and immutable contracts.
- [ ] Run focused tests until green.

### Task 2: Persistence model, migration, repository, and fakes

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/analytics.py`
- Modify: `backend/app/business/ports.py`
- Modify: `backend/app/repositories/analytics.py`
- Modify: `backend/app/repositories/unit_of_work.py`
- Modify: `backend/app/repositories/scope.py`
- Modify: `backend/app/repositories/audit.py`
- Modify: `backend/tests/fakes.py`
- Create: `backend/alembic/versions/0006_scenario_analysis.py`
- Test: `backend/tests/unit/test_scenario_repository.py`

**Interfaces:**
- Produces immutable Scenario storage, scoped get/list, atomic `add_if_absent`, and scenario-aware audit visibility.

- [ ] Write failing tests for scoped visibility, idempotent insertion, no update/delete port, and audit scope.
- [ ] Run focused tests and confirm expected failures.
- [ ] Extend the model and repository, then add migration `0006` without editing earlier migrations.
- [ ] Run focused tests and model/import checks until green.

### Task 3: Scenario business service

**Files:**
- Create: `backend/app/business/simulation/service.py`
- Modify: `backend/app/business/simulation/__init__.py`
- Modify: `backend/app/composition.py`
- Test: `backend/tests/unit/test_scenario_service.py`

**Interfaces:**
- Produces `ScenarioService.preview()`, `create()`, `get()`, and `list()`.
- Consumes existing AnalyticsService, UnitOfWork repositories, SecurityContext, and request ID context.

- [ ] Write failing tests for observed and forecast baselines, stale historical opt-in, provenance, scope, source Signal/Incident validation, idempotent retry, immutable new saves, server recomputation, and transactional audit.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement authoritative baseline resolution and transactional creation.
- [ ] Run focused tests until green.

### Task 4: API and authorization

**Files:**
- Modify: `backend/app/schemas/domain.py`
- Modify: `backend/app/api/deps.py`
- Create: `backend/app/api/v1/scenarios.py`
- Modify: `backend/app/api/v1/mappers.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/integration/test_scenario_api.py`

**Interfaces:**
- Produces the four `/api/v1/scenarios` endpoints with strict schemas, pagination, allowlisted filters, permission checks, 404 scope behavior, and conflict-safe idempotency.

- [ ] Write failing API tests for preview/create/get/list, auth, invalid assumptions/type/period, stale forecast opt-in, scope, source access, unknown fields, and retry idempotency.
- [ ] Run focused tests and confirm expected failures.
- [ ] Add schemas, dependencies, mappers, and routes without business rules in controllers.
- [ ] Run API tests until green.

### Task 5: Frontend scenario flow

**Files:**
- Create: `frontend/src/features/scenarios/types.ts`
- Create: `frontend/src/features/scenarios/api.ts`
- Create: `frontend/src/features/scenarios/hooks.ts`
- Create: `frontend/src/features/scenarios/components/scenario-workbench.tsx`
- Create: `frontend/src/features/scenarios/components/scenario-workbench.test.tsx`
- Create: `frontend/src/app/scenarios/page.tsx`
- Modify: `frontend/src/app/dashboard/page.tsx`
- Modify: `frontend/src/app/signals/[id]/page.tsx`
- Modify: `frontend/src/components/site-header.tsx`

**Interfaces:**
- Produces observed/forecast preview/save UX with fixed assumptions, provenance, neutral comparison, stale/historical presentation, disclaimer, and entry links.

- [ ] Write failing component tests for controls, preview states, stale labels, disclaimer, save, source Signal context, and API errors.
- [ ] Run focused frontend tests and confirm expected failures.
- [ ] Implement feature modules and routes without client-side authoritative calculations.
- [ ] Run frontend tests, lint, and typecheck until green.

### Task 6: Documentation and architecture decision

**Files:**
- Create: `docs/SCENARIO_ANALYSIS.md`
- Create: `docs/ADR/0018-immutable-scenario-provenance.md`
- Modify: `docs/ADR/README.md`
- Modify: `docs/API.md`
- Modify: `docs/BUSINESS_LOGIC.md`
- Modify: `docs/DATABASE.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/TESTING.md`
- Modify: `docs/ROADMAP.md`

**Interfaces:**
- Documents formula, provenance, validity/freshness split, immutability, idempotency, scope, audit, UI wording, demo, and exact verification commands.

- [ ] Replace speculative Phase 2 scenario text and remove `FLOW_REDISTRIBUTION` contradictions.
- [ ] Document Scenario ≠ Forecast/Recommendation and referral change ≠ overload/capacity deficit.
- [ ] Run repository searches for unsupported claims and obsolete scenario types.

### Task 7: Migration, regression, and real-data demo

**Files:**
- Test/verify all files changed above.

**Interfaces:**
- Produces reproducible evidence for the Phase 7 final report.

- [ ] Run backend unit/integration/security suites, Ruff, mypy, and import-linter.
- [ ] Run frontend test, lint, typecheck, and production build.
- [ ] Verify migration `0006` on a clean database, an existing Phase 6 database, and downgrade/upgrade.
- [ ] Exercise observed Q1 and persisted stale forecast scenarios against current data.
- [ ] Verify retry idempotency, separate intentional saves, audit, scope denial, and no Signal/Incident mutation.
- [ ] Record exact commands, counts, values, and any design deviations.

