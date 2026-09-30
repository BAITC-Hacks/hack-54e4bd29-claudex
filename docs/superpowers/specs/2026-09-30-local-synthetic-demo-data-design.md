# Local synthetic demo data as the primary dataset

## Decision and intent

MedSignal's local demonstration must use one coherent synthetic dataset as the
primary source for data-bearing screens. The user approved local-only scope and
a new isolated Compose project with fresh volumes; the current local project's
database, volumes, and work history must be preserved. A successful demo must
show consistent map, KPI, analytics, organization, signal, and forecast values
through the existing authenticated backend APIs. This is not production data or
production readiness.

## Current state and chosen approach

The existing acceptance fixture creates two abstract regions (`R-A`, `R-B`),
three organizations, and small exact-count deliveries. The Situation Center
currently has a separate 12-point frontend demo layer. The two API regions do
not match the Kazakhstan map's geographic lookup, so switching to the API layer
shows no markers. Forecast history is published by a separate synthetic
fixture. These independent sources explain the inconsistency.

Use a **separate local-demo synthetic profile** that seeds canonical entities
and publishes contract-valid source deliveries through the existing import and
mapping pipeline. Read them through existing backend APIs. Do not add a mock API
server or frontend response interception. Do not replace the strict Phase 8
acceptance fixture or change its established counts and verifiers. A frontend-
only fixture is simpler initially but cannot reliably preserve scope, action
state, analytics totals, and forecast provenance; keeping the current hybrid
would retain contradictory numbers.

## Data profile and provenance

- The profile contains 12 geographically identifiable Kazakhstan regions,
  matching the map's existing coverage, and fictional medical organizations
  assigned to those regions. Actual geography labels may be used; organization
  identities and all measured values are invented. No real patients or medical
  records are included.
- A deterministic generator produces referrals, waiting, and refusals over an
  explicitly historical period consistent with the current Situation Center
  query. It produces source files and manifests satisfying the existing import
  contracts. Expected totals are derived from the generated manifests and
  imported rows, never typed independently into UI components.
- Canonical region and organization seed identities, source identifiers, and
  published exact mappings use one shared local-demo profile. The bootstrap
  verifies that every imported regional/organization source key maps to the
  intended canonical entity. Local test identities receive scopes referencing
  seeded entities, then global, regional, and organization roles exercise the
  existing authorization checks. Acceptance-profile identities are unchanged.
- Synthetic signals refer to seeded organizations and periods. Their evidence
  and algorithmic explanation must agree with generated observations; human
  status changes remain ordinary persisted backend actions. No AI action is
  automatic.
- The local-demo profile publishes enough synthetic referral history for the
  existing forecast pipeline to store its 7-day GLOBAL
  `DAILY_REFERRAL_COUNT` result. Forecast output dates derive from the input
  period; model selection, MAE, and baseline MAE come from that pipeline, not
  hand-edited values. The strict acceptance forecast fixture stays unchanged.
  The UI keeps the historical/stale and medical-limitations disclosures. No
  new model or organization-specific forecast is introduced.
- No bed-capacity, discharge-date, or medical-advice values are invented.
  Unavailable fields stay unavailable. Copilot remains disabled for this task;
  the existing algorithmic signal explanation remains visible and no paid LLM
  call occurs.

## Application behavior

In a local synthetic build (`APP_ENV=local`,
`NEXT_PUBLIC_APP_ENV=test`, `NEXT_PUBLIC_SYNTHETIC_DEMO=true`), all existing
data-bearing screens use the same authenticated APIs backed by the new profile:
Situation Center, Analytics, Regions/Queue, Organizations, Signals, Forecast,
and Scenarios where they consume those APIs. The landing page and login do not
gain invented counters. Existing API contracts and auth architecture remain
unchanged.

The Situation Center map uses only API-derived regional points and their
canonical geography. Remove the frontend-only `DEMO_MAP_REGIONS` numbers and
the “Демо-слой / Данные системы” switch. Selecting a marker changes the same
backend region scope used by KPI, charts, and linked screens. If a region lacks
a verified map location, disclose that it is unmapped; never assign arbitrary
coordinates. Keep a compact, persistent “Синтетические данные” provenance
label so the dataset is not mistaken for official statistics. API failure
shows an unavailable state, never a hard-coded fallback value.

The profile is guarded against non-local execution and is not selected in a
production build. No security admission, CI policy, OIDC contract, API schema,
or storage architecture changes are part of this design.

## Isolation and promotion of the local demo

Prepare a fresh disposable `phase8-*` Compose project with new project-scoped
volumes using the existing acceptance preparation and safety checks. Build the
frontend with both public flags, not runtime-only variables. To avoid two full
stacks competing for resources, stop—but do not delete—the current local
project after its identity and state are recorded. Start the new project on a
temporary loopback port, bootstrap and verify it, then make it the local
`127.0.0.1:8080` demo endpoint. If bootstrap or verification fails, do not
promote the new project; the preserved old project can be started again. Never
delete or reset the old volumes as part of this work. If the existing launcher
cannot safely switch the loopback binding, report that limitation rather than
changing network boundaries or bypassing its safety checks.

## Verification and acceptance criteria

1. Pure tests prove deterministic generation, local-only guards, unique
   synthetic identities, manifest counts/hashes, and exact mapping coverage.
   Existing strict Phase 8 acceptance tests remain unchanged and passing.
2. In the fresh stack, migrations, readiness, synthetic bootstrap, publication,
   scope verification, and forecast DB/API verification pass. Compare API
   aggregates with the generated manifests and published rows; do not use
   expected constants from an unrelated fixture.
3. A real Keycloak browser journey confirms that the map and KPI/analytics
   share regional values, organization navigation retains context, a signal
   action persists after reload, and the forecast card displays pipeline-
   derived validation fields. Copilot disabled state works without a paid call.
4. The map has no frontend-only synthetic counts or external country tiles.
   Each visible marker has a canonical API region; synthetic provenance is
   visible on the main screens. Zero executed or skipped tests do not count as
   passing evidence.
5. Frontend lint, typecheck, unit tests, and production build plus affected
   backend/pipeline tests are run. Existing unrelated failures are reported
   separately from new regressions. No push, main merge, deployment, or
   production-readiness claim follows automatically.

## Boundaries

Do not change the forecast algorithm, Signal Engine, Copilot API, auth model,
PostgreSQL/ClickHouse storage model, production data sources, security gates,
or existing acceptance profile solely to achieve a visually full demo. This
work creates a local synthetic data profile and connects the current UI to its
real API results; it does not introduce another application runtime.
