# ADR-0017. Evaluation windows, global scope and Signal deduplication

**Status:** Accepted  
**Date:** 2026-09-17  
**Supersedes:** the deduplication and stale-data behavior described in
[ADR-0008](0008-signal-engine-three-sources.md)

## Context

Phase 6 can evaluate only the facts actually available after Phases 3–5.
Organization mappings are incomplete, waiting data is a single supplied
snapshot, and the operational event sources end in March 2025. Creating
hospital-scoped signals or pretending those rows are current would be false.

Updating an existing Signal on every run also destroys the historical evidence
used to make a decision. The engine needs replay-safe creation while preserving
the exact rule and input watermark that produced each Signal.

## Decision

The first production Signal Engine policy is:

- real evaluations are `GLOBAL`; no synthetic hospital mapping is created;
- `DATA_STALE` is evaluated first. A stale source suppresses operational spike
  detection for that source;
- a stale Forecast never creates `FORECAST_INFLOW_GROWTH`;
- `DATA_QUALITY_DEGRADED` requires an explicit numerator, eligible denominator
  and denominator code. A numerator-only quality finding returns
  `INSUFFICIENT_DATA`;
- spike evaluation uses the last seven complete days and the median of eight
  preceding, non-overlapping seven-day windows. All reference days are strictly
  before the evaluation window;
- thresholds 20%, 35% and 50%, and freshness limits 72h/168h, are versioned,
  configurable analytical policy. They are not medical standards or an SLA;
- every Signal stores the rule code, rule version, complete configuration
  snapshot, evidence, periods and source watermark;
- deduplication identity is a deterministic hash of signal type, explicit
  scope, evaluation window, rule code/version and source watermark;
- an exact replay returns `SKIP_IDEMPOTENT` and does not modify the existing
  Signal. A changed watermark creates a new Signal and retains the prior one;
- database uniqueness on `signals.dedup_key` is the final race-condition guard;
- `BASELINE_DEVIATION` and `WAITING_AGE_SPIKE` are deferred.

## Consequences

Evaluation is reproducible and safe to replay. A closed human decision is never
silently reopened or rewritten by automation. The feed may contain successive
Signals from the same rule when their evidence watermark changes; this is
intentional traceability rather than duplication.

Global Signals are visible only to users whose resolved `SecurityContext` has a
global data scope. Region and hospital scopes receive `404`, preventing leakage
of system-wide aggregates.

The policy cannot yet identify a specific hospital requiring action. This is an
explicit limitation until approved organization mappings and sufficient
history exist.

## Revisit

Revisit the scope when official organization mappings are available. Revisit
spike windows and thresholds only through a new rule version with historical
backtesting. Add waiting-age signals only after multiple confirmed queue
snapshots establish a real time axis.
