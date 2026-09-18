# Phase 8 — Demo, Security and Production Readiness Design

## Status

Approved on 2026-09-17. This specification hardens the accepted Phase 0–7
system. It does not add new medical, analytical or ML product capabilities.

## Goal

Make MedSignal reproducibly deployable, recoverable, security-reviewed,
performance-measured on the real Q1 2025 dataset and demonstrable through the
existing human-in-the-loop workflow.

## Non-goals

Phase 8 does not add bed/capacity modelling, patient-level prediction, new ML
targets, LLMs, automatic Incidents, fuzzy mappings, Kubernetes, Vault or new
product modules. Historical data and stale Forecasts remain visibly stale.

## Baseline and migration policy

The starting point is commit `aca79d8daa0061c045be37bd4054cd4a6ba5a60c`.
Accepted migrations `0001–0006` remain immutable. Current PostgreSQL schemas
created from those migrations are correct. Alembic drift is caused by stale ORM
metadata:

- Phase 3 counters are `BIGINT` in PostgreSQL but inferred as `INTEGER` in ORM;
- server defaults present in migration `0003` are missing from ORM metadata;
- two Forecast indexes created by migration `0004` are missing from ORM metadata.

Models will be aligned to the accepted schema. No `0007` is created solely for
this repair. Success is a clean `alembic check` on both an existing and a fresh
database.

## Deployment architecture

`docker compose up` remains the local/demo workflow. A production overlay
selects existing production Docker stages, removes source bind mounts, applies
production runtime settings and adds focused container hardening. It is an
overlay, not a duplicated stack.

Explicit `container_name` declarations are removed after dependency searches
and smoke tests prove no caller relies on them. Compose project names then
isolate clean deployment, restore and demo verification resources. All Phase 8
temporary resources use the `phase8-` namespace.

PostgreSQL and ClickHouse migrations become one-shot startup dependencies.
ClickHouse migrations `001–005` run automatically and idempotently before API,
worker and data tooling can use analytical storage. Data import remains an
explicit command and the source directory is mounted read-only.

## Environment and identity modes

Local/demo mode uses the clearly labelled development realm and synthetic
credentials. Production mode never imports the development realm and requires
external secrets, HTTPS public URLs, an explicit CORS allowlist and trusted
hosts. Real DNS, certificates, WAF/firewall/VPN and corporate IdP credentials
remain external dependencies.

The development realm provides synthetic identities for ADMIN,
HEALTH_AUTHORITY, REGIONAL_ANALYST and HOSPITAL_MANAGER/HOSPITAL_ANALYST. Their
Keycloak subjects map to deterministic synthetic PostgreSQL scopes. Real token
tests verify GLOBAL, REGION and HOSPITAL isolation and IDOR behaviour.

Corporate SSO is documented as `EXTERNAL DEPENDENCY / NOT CONFIGURED` until an
actual identity provider is connected.

## Configuration safety

Configuration is classified as required, optional, development-only or
production-required. Non-local startup fails when debug/test authentication,
placeholder secrets, wildcard/empty CORS, empty trusted hosts, HTTP public OIDC
issuer or missing HTTPS boundary settings are detected. Internal plaintext
connections may be accepted only as a documented private-network deployment
choice; they are never described as encrypted.

## Backup and restore

Backup tooling covers PostgreSQL, ClickHouse and MinIO. A backup is accepted
only after restore into isolated `phase8-*` destinations and verification of
representative data and counts. Restore never targets the primary environment.
Redis is excluded because it remains cache, broker, rate-limit and task-result
transport; persistent operation state lives in PostgreSQL.

## Security and privacy verification

The review covers authentication, authorization, IDOR, scope bypass, mass
assignment, dynamic query allowlists, CORS, file/path boundaries, sensitive
logging and error leakage. Container images are scanned with a pinned Trivy
container when Docker Scout cannot run without authentication. Scanner version,
image digest and findings are recorded.

After controlled import, ClickHouse schemas and data paths are rechecked to
prove raw `hospitalization_code` and `patient_seq_no` do not enter analytical
storage. Signals, evidence, Scenarios, Audit and logs are checked for sensitive
identifiers. Existing small-cell suppression remains mandatory.

## Observability

Existing structured logs, request IDs, readiness and persistent operations are
retained. Focused low-cardinality metrics fill gaps for HTTP requests and
background outcomes. `/metrics` remains inaccessible through public nginx.
Operators receive exact commands to distinguish API, PostgreSQL, ClickHouse,
Redis, worker, import, Signal Engine and forecast failures.

## Performance

Performance is measured only after the real allowlisted core datasets are
imported from `C:\Users\zhasy\Downloads\data` through the read-only mount. The
starting load is 20 concurrent users and is an engineering benchmark, not an
SLA. Every result records endpoint, concurrency, request count, p50/p95/p99,
error rate, cache state and dataset size. Background import, Signal Engine and
forecast timings are reported separately.

## E2E and demo

The primary demo uses real Q1 2025 history and explicitly shows stale freshness:

1. HEALTH_AUTHORITY login;
2. Situation Center and data freshness;
3. Forecast validity versus freshness;
4. DATA_STALE Signal and deterministic evidence;
5. acknowledge;
6. historical Scenario preview and save;
7. explicit Incident creation;
8. assignment and status transition;
9. Audit verification.

Synthetic spike data is added only if the historical flow cannot demonstrate
an active spike and must be isolated and labelled. The safe reset mechanism
operates only on an isolated demo project or explicit Phase 8 manifest. It does
not delete real imported facts or source files.

## Acceptance evidence

`docs/PHASE_8_ACCEPTANCE.md` uses only:

- `PASS`
- `FAIL`
- `NOT TESTED`
- `EXTERNAL DEPENDENCY`
- `NOT APPLICABLE`

Documentation or a template alone never produces PASS. A presentation metrics
document is generated from actually executed verification results. Exact
commands and environment identifiers are included.

## Safety boundary

The source dataset is always read-only. Existing project volumes are not
deleted. Clean deployment and restore use new Compose projects, databases and
buckets with unambiguous `phase8-` names. Git reset/clean and destructive
operations on accepted state are forbidden.
