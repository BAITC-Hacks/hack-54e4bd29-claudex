# Phase 6 Signal Engine Design

**Status:** Approved on 2026-09-17

## Goal

Add a deterministic, evidence-backed Signal Engine to the existing MedSignal
modular monolith. Signals support human review and never claim a confirmed
hospital overload or make a medical or managerial decision.

## Reused foundations

- Existing `Signal`, `SignalExplanation`, `Incident`, `Action`, Audit Log and
  optimistic concurrency.
- Existing Signal state machine and server-computed transitions.
- Existing RBAC, `SecurityContext`, PostgreSQL Unit of Work and scoped
  repositories.
- Existing ClickHouse aggregate repositories, Phase 4 data quality/freshness
  metadata and Phase 5A forecast freshness contract.
- Existing Celery, `SystemOperation`, request ID propagation and frontend
  Signal pages.

## Scope correction

Signals and Incidents gain explicit `GLOBAL`, `REGION` or `HOSPITAL` scope.
Existing rows are backfilled as `HOSPITAL`. A global object has no region or
hospital ID; a regional object has only a region ID; a hospital object has a
hospital ID. Database constraints enforce these combinations. No fictitious
hospital mapping is permitted.

All signals generated from the current real dataset are global. They are
visible only to users with a permitted global scope. Narrower scopes are
disabled until canonical mappings are trustworthy.

## Rules

### Data freshness

`DATA_STALE:v1` compares the latest successful source timestamp with a
source-specific maximum age. Initial configurable policy:

- referrals: 72 hours;
- refusals: 72 hours;
- waiting: 168 hours;
- treated: disabled until delivery-period semantics are confirmed.

Severity is WARNING above 1x max age, HIGH above 2x and CRITICAL above 4x.
These values are analytical policy, not a medical norm or supplier SLA.

### Data quality

`DATA_QUALITY_DEGRADED:v1` uses only persisted, formalized quality rules with
an explicit affected-row numerator and an explicit eligible-row denominator.
Severity is WARNING at 1%, HIGH at 5% and CRITICAL at 10%. Expected conditional
nulls are excluded. If denominator semantics are absent, the evaluator returns
`INSUFFICIENT_DATA` and does not create a Signal. In particular, the 104,644
historical chronology findings do not trigger merely because the count is
large.

### Observed spikes

`REFERRAL_SPIKE:v1` and `REFUSAL_SPIKE:v1` compare the latest seven complete
source days with the median of the eight immediately preceding, non-overlapping
seven-day windows. All reference windows end strictly before the evaluation
window. Minimum history is eight complete reference windows. The current and
reference windows never overlap.

Severity is WARNING at +20%, HIGH at +35% and CRITICAL at +50%. Partial days
are excluded. If source data is stale, operational spike evaluation is
suppressed and only `DATA_STALE` may be emitted.

`BASELINE_DEVIATION` is omitted because it duplicates the two spike rules with
the current metrics. `WAITING_AGE_SPIKE` is omitted because the current waiting
data is a snapshot rather than a historical queue series.

### Forecast growth

`FORECAST_INFLOW_GROWTH:v1` compares summed forecast points with the stored
baseline over the same horizon. It uses the 20%/35%/50% severity thresholds.
It can emit only from a current, valid forecast. A stale or missing forecast is
suppressed. A baseline-selected model remains labelled as a baseline and uses
the existing `STATISTICAL` source type; a genuine ML model uses `ML_BASED`.

## Evidence and explanation

Each Signal stores scope, observed/evaluation/reference periods, actual and
baseline values, absolute and percentage deltas, rule code/version, a rule
configuration snapshot, structured evidence, source, data watermark and data
freshness. `SignalExplanation` remains the deterministic human-readable layer.
No LLM is used and no causal explanation is fabricated.

## Idempotency

The deduplication key is SHA-256 over signal type, scope, scope ID, evaluation
window, rule version, data watermark and quality-rule code when applicable.
Exact replay is a no-op protected by a unique database index. A new window or
watermark creates a new historically traceable Signal; previous history is not
overwritten. This supersedes the old update-on-repeat wording in ADR-0008.

## Lifecycle and Incident integration

- acknowledge maps to `IN_PROGRESS`;
- resolve maps to `CLOSED` with `RESOLVED` disposition;
- dismiss maps to `CLOSED` with `DISMISSED` disposition;
- reopen follows the existing `CLOSED -> IN_PROGRESS` transition.

All human transitions require permission, expected version and reason, and are
committed atomically with Action and AuditEvent records.

`Create Incident from Signal` is an explicit human action. The Incident
inherits the Signal scope and remains linked through `signal.incident_id`.
Repeated creation is idempotent. No automatic management action occurs.

## Execution

Manual CLI and a Celery task call the same orchestration service. `SystemOperation`
persists run status and structured outcomes. Evaluators produce candidates;
the orchestrator performs deduplicated persistence. One evaluator failure is
reported without corrupting successful evaluator results. No scheduler is
introduced and periodic execution is disabled by default.

## Current-data expectation

The current source and forecast are historical. Data-staleness signals may be
created. Operational spike signals are suppressed while source data is stale.
The stale forecast cannot create `FORECAST_INFLOW_GROWTH`. Data-quality signals
are created only where a denominator-backed measurable rule exists.
