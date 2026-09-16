# Phase 5A Short-Horizon Referral Forecast — Design

## Decision

Phase 5A forecasts the system-wide daily count of planned-hospitalization
referrals for the next seven calendar days. The current referral fact contains
`registration_dt` and source organization identities, but no authoritative
region identifier. Canonical hospital mapping is incomplete. A region-level
target would therefore require an unapproved join and is rejected.

The result is an experimental short-horizon operational forecast. It is not a
hospital-overload, bed-availability, patient-level, annual, or medical forecast.
Only users with global data scope may read the global forecast.

## Boundaries

The `ml/` package owns deterministic feature construction, baselines,
walk-forward validation, metrics, the single tabular model, model selection and
artifact serialization. It does not import `backend.app` and does not know about
HTTP, RBAC, PostgreSQL or ClickHouse.

The backend business module declares forecast contracts and ports. Repository
implementations read aggregate referral history from ClickHouse and persist
append-only model/forecast metadata and forecast points in PostgreSQL. The API
only authenticates, validates, calls the query service and serializes results.

Training and bulk generation run in the worker or explicit CLI command. The API
container does not install ML dependencies. MLflow records experiments and the
selected candidate. The dashboard reads the latest persisted result.

## Dataset and features

The authoritative source is `fact_referral_events`, grouped by
`toDate(registration_dt)`. The builder fills absent calendar dates with zero,
records those dates in dataset metadata, and emits features using only earlier
observations: `lag_1`, `lag_2`, `lag_3`, `lag_7`, `rolling_mean_7`,
`rolling_std_7`, and `day_of_week`. Feature schema version is
`referrals_daily_v1`.

The source watermark contains completed referral import IDs, hashes and latest
completion time from PostgreSQL. No source event or patient identifier enters
the ML dataset, logs, MLflow parameters or forecast response.

## Evaluation and selection

Validation is expanding-window rolling origin with a seven-day validation
horizon and folds derived from available dates. The default minimum training
window is 42 days. All candidates receive identical folds.

Candidates are naive last value, weekly naive, seven-day moving average, and
one `HistGradientBoostingRegressor`. Metrics are MAE and WAPE (primary), RMSE
(secondary), overall and per fold. WAPE is explicitly undefined when the sum of
absolute actual values is zero.

The strongest baseline is the baseline with the smallest MAE, then WAPE, then
RMSE. ML is selected only when both MAE and WAPE improve by at least 2% over
that baseline. Equal or near-equal performance selects the baseline.

## Persistence and API

`model_versions` stores algorithm, feature schema, MLflow run ID, training
period, metrics, baseline metrics and selection rationale. The existing
`forecasts` table becomes a run header that supports GLOBAL, REGION and
HOSPITAL scopes, while Phase 5A writes only GLOBAL rows. `forecast_points`
stores immutable date/value pairs and the baseline value. New runs never update
or delete old runs.

`GET /api/v1/forecasts/referrals/latest` returns the latest valid global run.
It requires `forecast.read` and global data scope. Out-of-scope and missing
results return 404. Responses include model version, selected model, metrics,
watermark, input period, horizon, generated time, historical context, forecast
points, baseline points and limitations.

## Failure behavior

Training fails without at least one valid fold, without a completed referral
watermark, or when MLflow/persistence cannot record provenance. A failed task
does not replace the last valid forecast. Undefined WAPE is reported and cannot
be hidden or coerced to zero.

## UI

The existing dashboard receives one forecast card and combined accessible chart.
Copy uses “Краткосрочный прогноз потока направлений” and states that the forecast
uses about three months of history and has no validated annual seasonality. A
404 displays an unavailable-state explanation; it is never rendered as zero.

