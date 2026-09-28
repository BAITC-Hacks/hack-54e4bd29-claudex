# Phase 7 Scenario Analysis Design

## Purpose

Phase 7 adds a deterministic, human-triggered calculation that compares an authoritative referral baseline with one of four hypothetical inflow changes. It is descriptive decision support: it is not a forecast, recommendation, capacity model, overload assessment, or patient-level simulation.

## Accepted decisions

- Extend the existing PostgreSQL `Scenario` entity.
- Support only `REFERRAL_INFLOW_CHANGE`.
- Run preview and save synchronously; Celery is not involved.
- Support assumptions `-0.20`, `-0.10`, `0.10`, `0.20` only.
- Calculate with `Decimal`, `ROUND_HALF_UP`, and four decimal places.
- Preview is read-only and unaudited.
- Save reacquires the baseline and recalculates on the server.
- Saved scenarios are immutable.
- `(created_by, client_request_id)` is the retry-idempotency key.
- `source_signal_id` and `source_incident_id` are nullable and never cause automatic domain mutations.
- Use Phase 6 GLOBAL/REGION/HOSPITAL scope semantics without fuzzy or fabricated mappings.

## Baseline semantics

### Observed

The request identifies a permitted scope and inclusive date range. The server calls the existing referral analytics path and sums its aggregate time-series points. The client cannot submit an authoritative baseline value. The scenario stores the exact period, completed-import watermark, sources, and limitations returned by analytics.

### Forecast

The request supplies only a persisted `forecast_id`. The server requires target `DAILY_REFERRAL_COUNT`, structural `Forecast.status == VALID`, a complete period/watermark, and a scope visible to the caller. `Forecast.status` expresses model/result validity. Temporal freshness is independently derived from `forecast_end` and stored as `CURRENT` or `STALE`.

A stale forecast remains a valid historical artifact. It can be used only when the request explicitly enables historical analysis. The response and saved scenario identify it as historical and stale; it is never described as current.

## Calculation

`calculated_value = quantize(baseline_value * (1 + assumption_value), 0.0001, ROUND_HALF_UP)`

`delta_absolute = quantize(calculated_value - baseline_value, 0.0001, ROUND_HALF_UP)`

`delta_percent = assumption_value`

The formula is versioned as `referral_inflow_change.v1`.

## Persistence

Migration `0006` extends `scenarios`; accepted migrations remain unchanged. The record stores explicit scope, baseline/result values, baseline provenance, optional forecast provenance, independent freshness, source links, versioned limitations, and `client_request_id`. The repository exposes add/get/list/find-by-idempotency only; no update or delete operation exists.

Scenario creation and `SCENARIO_CREATED` audit insertion use one PostgreSQL Unit of Work. A retry with the same `(created_by, client_request_id)` returns the existing scenario without another audit event. A new intentional save uses a new request UUID and creates a new immutable record.

## Security and scope

- GLOBAL requires a global `SecurityContext`.
- REGION and HOSPITAL require access to the selected canonical scope.
- A source Signal or Incident must be visible and have exactly the selected scope.
- If both source objects are supplied, the Signal must belong to the Incident.
- Out-of-scope objects are reported as not found.
- Scenario list/get and scenario audit visibility apply the same scoped-entity predicate as Signal and Incident.

## API

- `POST /api/v1/scenarios/preview`
- `POST /api/v1/scenarios`
- `GET /api/v1/scenarios`
- `GET /api/v1/scenarios/{id}`

Requests contain baseline references, scope, the assumption, and optional source IDs. They do not contain authoritative calculated values. List filtering is allowlisted and paginated.

## Frontend

The `/scenarios` route supports observed and forecast baselines, four fixed assumption controls, preview, explicit save, provenance, neutral comparison, historical/stale labels, and the required disclaimer. The Situation Center and Signal detail link to it. Signal evidence remains separate from scenario baseline semantics. No Incident entry point is added in Phase 7.

## Required wording

Every preview and saved scenario displays:

> Расчётный сценарий. Не является прогнозом или рекомендацией. Решение принимает уполномоченный сотрудник.

It also states that changing referral inflow does not model beds, admissions, discharges, length of stay, staffing, occupancy, or capacity deficits.

## Non-goals

No Celery calculation, new ML model, LLM, free-form percentages, flow redistribution, refusal/waiting/bed/staff scenarios, optimization, recommendation, overload claim, automatic Incident creation, or automatic Signal/Incident mutation.

