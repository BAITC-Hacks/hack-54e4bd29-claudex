# Phase 6 Signal Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement deterministic, scoped and idempotent operational Signals with human review, Incident traceability, Celery execution and Situation Center presentation.

**Architecture:** Rule evaluators consume aggregate ports and return immutable candidates. A Signal evaluation service enforces stale-source suppression and persists candidates through the existing Unit of Work, while APIs only read persisted results or execute human lifecycle operations. Existing Signal, Incident, Audit, RBAC, ClickHouse and forecast contracts are extended rather than replaced.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL, ClickHouse, Celery, Pydantic, pytest, Next.js, TypeScript, TanStack Query, Zod, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-17-phase6-signal-engine-design.md`

## Global Constraints

- Signal is evidence-backed decision support, not confirmed hospital overload.
- Stale source data suppresses operational observed-data spike signals.
- Stale forecasts never create operational forecast signals.
- Current generated signals are GLOBAL; no fictitious hospital mapping.
- Rule snapshots and versions are persisted on every Signal.
- No patient identifiers, medical recommendations, LLM output or automatic decisions.
- The 20%/35%/50% and 72h/168h values are configurable analytical policy, not medical norms or SLAs.

---

### Task 1: Pure rule contracts and evaluators

**Files:**
- Create: `backend/app/business/signals/contracts.py`
- Create: `backend/app/business/signals/policy.py`
- Create: `backend/app/business/signals/evaluators.py`
- Test: `backend/tests/unit/test_signal_evaluators.py`

**Interfaces:**
- Produces `EvaluationStatus`, `SignalCandidate`, `EvaluatorResult`, source-series and quality/forecast evidence contracts.
- Produces deterministic evaluators for freshness, quality, referral spike, refusal spike and forecast growth.

- [ ] Write failing tests for fresh/stale/boundary freshness; measurable/insufficient quality; normal/spike/partial-day/insufficient/no-leakage time series; current/stale/missing/baseline forecast; severity boundaries and deterministic deduplication input.
- [ ] Run the focused tests and verify failures are caused by missing contracts/evaluators.
- [ ] Implement minimal pure contracts, validated policy and evaluators.
- [ ] Run focused tests and refactor while green.

### Task 2: Aggregate input ports and adapters

**Files:**
- Modify: `backend/app/business/signals/contracts.py`
- Modify: `backend/app/business/ports.py`
- Create: `backend/app/repositories/signal_inputs.py`
- Modify: `backend/app/repositories/unit_of_work.py`
- Test: `backend/tests/unit/test_signal_input_repositories.py`

**Interfaces:**
- Produces methods to read complete daily referral/refusal aggregates, latest completed import watermarks, denominator-backed quality measurements and current forecast evidence.

- [ ] Write failing repository-contract tests for strict time-window ordering, complete days, quality denominator semantics and forecast freshness.
- [ ] Run focused tests and confirm RED.
- [ ] Implement ClickHouse/PostgreSQL adapters using aggregate queries only.
- [ ] Run focused tests and confirm GREEN.

### Task 3: Explicit scope, evidence and migration

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/signal.py`
- Modify: `backend/app/models/incident.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0005_signal_engine.py`
- Modify: `backend/app/repositories/scope.py`
- Modify: `backend/app/repositories/signals.py`
- Modify: `backend/app/repositories/incidents.py`
- Test: `backend/tests/unit/test_signal_repository_scope.py`

**Interfaces:**
- Extends Signal/Incident with explicit scope and Signal with rule/evidence/deduplication/disposition fields.
- Backfills accepted rows as HOSPITAL and enforces scope check constraints and a unique deduplication key.

- [ ] Write failing tests for global visibility, restricted scope denial, persisted evidence and duplicate key behavior.
- [ ] Run focused tests and confirm RED.
- [ ] Implement model/repository changes and the additive migration.
- [ ] Run focused tests and confirm GREEN.

### Task 4: Evaluation orchestration and idempotent persistence

**Files:**
- Create: `backend/app/business/signals/evaluation.py`
- Modify: `backend/app/business/signals/service.py`
- Modify: `backend/app/business/shared/events.py`
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/repositories/signals.py`
- Modify: `backend/tests/fakes.py`
- Test: `backend/tests/unit/test_signal_evaluation_service.py`

**Interfaces:**
- Produces `SignalEvaluationService.evaluate_all()` returning per-evaluator CREATED/NO_SIGNAL/SUPPRESSED/INSUFFICIENT_DATA/FAILED outcomes.
- Persists exact replays idempotently and audits created Signals.

- [ ] Write failing orchestration tests for stale-source suppression, isolated evaluator failure, duplicate replay, new watermark and audit creation.
- [ ] Run focused tests and confirm RED.
- [ ] Implement orchestration and UoW persistence.
- [ ] Run focused tests and confirm GREEN.

### Task 5: Human lifecycle and Incident workflow

**Files:**
- Modify: `backend/app/business/signals/service.py`
- Modify: `backend/app/business/incidents/service.py`
- Modify: `backend/app/business/ports.py`
- Modify: `backend/app/repositories/incidents.py`
- Modify: `backend/app/repositories/signals.py`
- Modify: `backend/app/security/permissions.py`
- Modify: `backend/tests/fakes.py`
- Test: `backend/tests/unit/test_signal_workflow.py`

**Interfaces:**
- Produces acknowledge/dismiss/resolve/reopen and create-Incident-from-Signal operations with expected-version concurrency, assignment and atomic Action/Audit writes.

- [ ] Write failing tests for every valid/invalid transition, permissions, duplicate Incident creation, traceability, assignment/status and audit events.
- [ ] Run focused tests and confirm RED.
- [ ] Implement minimal workflow operations using the current UoW.
- [ ] Run focused tests and confirm GREEN.

### Task 6: CLI, Celery and API

**Files:**
- Create: `backend/app/cli/__init__.py`
- Create: `backend/app/cli/signals.py`
- Modify: `backend/app/workers/tasks.py`
- Modify: `backend/app/workers/celery_app.py`
- Modify: `backend/app/composition.py`
- Modify: `backend/app/api/v1/signals.py`
- Modify: `backend/app/schemas/domain.py`
- Modify: `backend/app/api/v1/mappers.py`
- Test: `backend/tests/integration/test_signal_engine_api.py`
- Test: `backend/tests/unit/test_signal_tasks.py`

**Interfaces:**
- Produces manual CLI, `signals.evaluate` Celery task, persisted operation outcomes and scoped Signal workflow endpoints.

- [ ] Write failing API/task tests for list/detail filters, global-scope denial, lifecycle endpoints, Incident creation and task request ID propagation.
- [ ] Run focused tests and confirm RED.
- [ ] Implement composition, CLI, task, schemas and routes.
- [ ] Run focused tests and confirm GREEN.

### Task 7: Situation Center Signal experience

**Files:**
- Modify: `frontend/src/types/domain.ts`
- Modify: `frontend/src/services/domain.ts`
- Modify: `frontend/src/hooks/use-domain.ts`
- Modify: `frontend/src/features/signals/labels.ts`
- Modify: `frontend/src/features/signals/signal-table.tsx`
- Modify: `frontend/src/app/signals/page.tsx`
- Modify: `frontend/src/app/signals/[id]/page.tsx`
- Modify: `frontend/src/app/dashboard/page.tsx`
- Create: `frontend/src/features/signals/signal-evidence.tsx`
- Create: `frontend/src/features/signals/signal-workflow.test.tsx`

**Interfaces:**
- Displays scope, structured evidence, freshness, rule version, limitations and permission-aware actions without client-side business calculations.

- [ ] Write failing component tests for active, empty, stale, suppressed/no-forecast and permission-restricted states.
- [ ] Run focused frontend tests and confirm RED.
- [ ] Implement Zod contracts, hooks and focused UI extensions.
- [ ] Run frontend tests, lint and typecheck until GREEN.

### Task 8: Documentation and architectural contracts

**Files:**
- Create: `docs/ADR/0017-explicit-signal-scope-and-idempotent-evaluation.md`
- Create: `docs/signals/SIGNAL_ENGINE.md`
- Modify: `docs/ADR/0008-signal-engine-three-sources.md`
- Modify: `docs/ADR/README.md`
- Modify: `docs/BUSINESS_LOGIC.md`
- Modify: `docs/API.md`
- Modify: `docs/DATABASE.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/TESTING.md`
- Modify: `.env.example`
- Modify: `Makefile`

**Interfaces:**
- Documents exact rules, threshold semantics, deduplication replacement, lifecycle, Incident/Audit integration, execution, current-data limitations and commands.

- [ ] Document implementation and ADR without unsupported capability claims.
- [ ] Add configuration examples and Make targets for manual evaluation.
- [ ] Run documentation/config checks and architecture contracts.

### Task 9: Migration and full verification gate

**Files:**
- Test: all backend/frontend tests and real environment only.

**Interfaces:**
- Verifies Phase 6 and all Phase 0–5A behavior.

- [ ] Run backend pytest, ruff, format check, mypy and lint-imports.
- [ ] Run frontend tests, lint, typecheck and production build.
- [ ] Upgrade a clean PostgreSQL database to head and exercise downgrade/upgrade for revision 0005.
- [ ] Upgrade the existing development database.
- [ ] Run the Signal Engine against current real data and capture every evaluator outcome without sensitive samples.
- [ ] Repeat against the same watermark and verify Signal counts do not change.
- [ ] Verify Signal → acknowledge → Incident → assignment/status → Audit through the public API.
- [ ] Report actual outcomes, deviations, performance, security/privacy and remaining limitations.
