# Current-branch acceptance implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Prepare reviewable ownership, image evidence, an isolated acceptance environment, aggregate verification, browser E2E and UX audit for the current MedSignal branch without publication.

**Architecture:** Keep the existing Compose topology; isolate acceptance with a `phase8-*` project and fresh volumes. Never treat a vulnerability report, a mocked browser flow, or synthetic data as production acceptance evidence.

**Tech Stack:** GitHub CODEOWNERS, Docker Compose, Python/pytest, Trivy, FastAPI, PostgreSQL, ClickHouse, Keycloak, Next.js, Playwright.

**Spec:** User attachment `43395c46-b14a-4ba0-b36b-bb3dd84fd629/Вставленный текст.txt` and confirmed U1/U2/U3 mapping.

## Global constraints

- Work only in `codex/medsignal-single-agent-20260926`; no push, PR, merge, deployment or GitHub settings changes.
- Do not weaken the HIGH image gate, suppress findings, or call an untested control PASS.
- No real medical dataset use without an approved dataset/path. Keep acceptance synthetic and artifacts free of credentials, tokens and medical data.
- Do not alter existing volumes; temporary resources use a `phase8-*` namespace.
- The user subsequently provided `TEAM_OWNERSHIP.md`; use its complete path matrix and preserve a repository copy at `docs/TEAM_OWNERSHIP.md`.

## Review focus

- CODEOWNERS last-match exceptions must assign Dockerfiles to U2 and SQL/Python manifests to U1 even inside another zone.
- Every image scan must identify the exact current HEAD image and scanner database; stale reports cannot count.
- Acceptance may not publish data-service ports or reuse local/production volumes.
- Aggregate verification must exclude failed HTTP responses from latency and fail on cross-scope/publication mismatch.
- Browser artifacts must exclude secrets and the test suite must run against real services, not API mocks.

## Tasks

### U2-02 Ownership and PR process

- [ ] Add a failing ownership contract test over representative paths, including exceptions and unassigned `@albqqd`.
- [ ] Add `.github/CODEOWNERS`, adjust PR template to require role-aware review and explicit gate evidence.
- [ ] Run ownership/security tests; commit only this unit.

### U2-01 Current image security audit

- [ ] Build backend, worker, MLflow, frontend and nginx from this HEAD; record image and base digests.
- [ ] Scan each with pinned Trivy and current DB. Classify all HIGH/CRITICAL and fixed versions.
- [ ] Check a compatible newer base only if evidence shows reduction; run relevant tests and runtime smoke before adopting.
- [ ] Update `docs/security/CURRENT_IMAGE_FINDINGS.md`; keep gate FAIL if unresolved; commit evidence/documentation.

### U2-03 Isolated acceptance environment

- [ ] Write failing tests for project/volume/port/credential isolation and migration/readiness evidence.
- [ ] Implement `scripts/operations/prepare_acceptance.py`; add `docs/acceptance/CURRENT_MAIN_ENVIRONMENT.md`.
- [ ] Exercise isolated startup and health if Docker is available; commit.

### U1-03B Aggregate verifier

- [ ] Add failing synthetic tests for waiting/organizations, snapshot and scope consistency, intersection, reconciliation, latency/failure accounting.
- [ ] Extend the read-only verifier and run on approved synthetic acceptance data.
- [ ] Record real-scale as NOT TESTED absent approved data; commit.

### U3-04 Browser E2E

- [ ] Add Playwright against the production Next build, real backend and test Keycloak in isolated acceptance.
- [ ] Exercise specified journeys at 390/768/1280; store only safe evidence.
- [ ] Run until stable; commit.

### U2-05 Browser CI

- [ ] After U3-04 passes locally, add a required job with readiness, zero/skip failure, safe artifact handling and teardown.
- [ ] Verify workflow syntax and local equivalent; commit.

### U3-05 User journey audit and final verification

- [ ] Audit all requested states and wording; update user journey and demo runbook.
- [ ] Run complete backend, pipeline/ML, frontend, infrastructure, integration and synthetic performance checks.
- [ ] Record exact PASS/FAIL/NOT TESTED and blockers; commit documentation.
