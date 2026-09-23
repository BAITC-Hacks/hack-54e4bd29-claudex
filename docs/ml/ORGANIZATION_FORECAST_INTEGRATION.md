# Gated organization forecast integration (R1)

Status: implemented callable backend path, disabled by default. This is not owner
approval or authorization to activate an operational model. M3, trusted model
registration and owner inputs remain release blockers. All positive R1 test
fixtures are synthetic; the legacy Q1 joblib model is not an admitted model.

## Entry points and gates

`ml.forecast_organization` is a Celery task with late acknowledgement and
worker-loss redelivery. Its server-side composition is
`build_organization_forecast_service()`. `ORGANIZATION_FORECAST_ENABLED=false`
returns `SUPPRESSED / ORGANIZATION_FORECAST_DISABLED` without opening storage.
There is no public training or artifact-loading API.

The request contains canonical hospital UUID, registered model version, mapping
version, delivery watermark, first predicted day (`origin`) and seven-day horizon.
It cannot supply policy, admission, object locations or model implementation.
Current-day origin, explicit consecutive complete history (at least 42 days),
source freshness, a SELECTED compatible ModelVersion and trusted admission are
required. Missing contracts, unknown coverage, stale data, unsupported admission,
invalid/nonfinite predictions and changed publication fail closed.

The production repository locks D's active mapping, then the source delivery
publication, and holds both through inference and commit. Reads use D's canonical
hospital projection and exact published import allowlist. Mapping, hospital and
model registration must remain valid; mapping/delivery are checked again before
persistence. No missing-day zero filling or inferred delivery cadence is used.

Existing global training and forecast semantics remain intact. Global history
uses the metadata `referral_history_import_ids` allowlist: legacy COMPLETED imports
without delivery are visible, new delivery imports require publication. Operational
referral/refusal spikes additionally require D's explicit complete coverage and
recheck publication under the same source lock during signal persistence. Legacy
history can establish staleness, but unknown coverage cannot create a spike.

## Trusted registration and object storage

Use the existing ModelVersion and its server-controlled
`validation_config.organization_forecast_v1`; there is no parallel model domain.
The registry schema is `organization-model-registry-v1` and contains:

- `model_version`, `model_type` (`ML`), `feature_schema_version`
  (`hospital-referrals-direct7-v1`), `hospital_ids`, `valid_from`, `valid_through`.
- `artifact` and `protocol` immutable object references; each reference has
  `key`, `version`, `sha256`. Corresponding `artifact_sha256` and
  `protocol_sha256` must match. `valid_through` includes all seven predicted days.
- `code_sha256`, `code_commit`, full M `report` and `policy`, and immutable
  `report_object` and `policy_object` references whose verified content equals
  those registered values.
- `review_objects`, keyed by each review's `evidence_ref`, with the same immutable
  object-reference shape. Policy sign-off, coverage and sealed-period records
  require verified external review and matching hashes/content. A PASS string
  supplied separately is never authority.

Objects come only from the configured model bucket, which must provide immutable
version IDs (versioning enabled). The adapter verifies returned object version,
SHA256 and a 64 MiB size bound before deserialization. References cannot select a
bucket, URL or local path. The loader accepts only the registered
HistGradientBoostingRegressor with the frozen 12-feature schema. No artifact is
loaded until registration, runtime, admission and all review checks succeed.

M's `evaluate_admission` determines status, reason codes and frozen policy.
Report/protocol/dataset/artifact/mapping hashes and model metrics are cross-bound.
The sealed train/validation/test ends must equal protocol splits, test start must
be validation end plus one day, and no known development interval may overlap the
sealed test. Registration must bind the actual requested hospital, model and date.
See [M admission contract](MONITORING_ADMISSION_CONTRACT.md).

## Runtime implementation binding

Before admission can return PASS and again before loading/inference, the adapter
reads actual deployed source bytes for `ml/monitoring.py`,
`ml/monitoring_contracts.py`, `ml/evaluation/monitoring.py` and
`ml/evaluation/admission.py`. It hashes each file and hashes the canonical JSON
map of relative filename to SHA256 (sorted keys, compact separators, UTF-8).
This actual digest must match both frozen protocol `implementation_sha256` and
registry `code_sha256`. No documentation digest is hardcoded into production.

Loaded function and source-defined method/property code objects are also compared
with definitions compiled from those source bytes without executing the compiled
module. This rejects an in-memory replacement of `features_at` even when disk and
registered hashes agree. Python, NumPy and scikit-learn runtime versions must equal
the existing protocol `dependency_versions`; no unsupported protocol keys were
added. Any deployment change requires corresponding trusted re-evaluation and
registration; changing documentation alone cannot admit it.

## Alert rule and weekly alignment

Forecast points retain M's selected prediction-error baseline (`weekly_naive` or
`mean7`) for charts. It is not substituted for the operational alert reference.
The organization-only signal reference is the sum of the 28 complete days before
the first predicted day divided by four. The frozen `referral-growth-v1` rule fires
only when all inclusive tests pass: reference >= 20, forecast minus reference >=
10, and seven-day forecast >= reference * 1.2. The comparison matches M directly,
including exact 20 percent equality. Existing global rule behavior is unchanged.

The episode anchor is protocol validation end plus one day (sealed test start),
which is M's **first predicted day**, not its last-observed-day forecast origin.
Signals are eligible only at this anchor plus a nonnegative multiple of seven
days. Other current-day forecasts can persist without producing an alert. Existing
Signal severity thresholds classify admitted alerts; a warning threshold other
than the frozen 20 percent fails closed in this path.

`ForecastEngineResult.organization_evidence` is an optional additive field;
organization inference requires its verified frozen policy and anchor. Signals
use `org-growth-v1` and record the full episode policy, 28-day reference method,
reference dates, cadence, anchor, protocol hash, severity configuration/version,
and separate displayed forecast baseline and operational reference. Forecast
watermarks retain public admission/provenance without private review locations.

## Idempotency and persistent operation state

The deterministic existing SystemOperation UUID binds hospital, target, first
predicted day, horizon, model, mapping and delivery watermark. A serialized short
PostgreSQL transaction commits RUNNING before computation. A second transaction
holds the same advisory lock through computation, recheck and persistence.
Concurrent retries wait and reuse an existing COMPLETED result, including redelivery
after commit but before Celery acknowledgement. FAILED and abandoned RUNNING
operations can be retried. Ordinary exceptions roll back all domain/completion
audit writes, then persist FAILED with a safe generic error; process termination
leaves RUNNING visible. Failure handling cannot overwrite a concurrent COMPLETED
result. A task lost before worker entry has no R1 reservation; there is currently
no R1 public enqueue endpoint.

Forecast, seven ForecastPoints, optional existing Signal and explanation, completed
SystemOperation result and completion/signal audit events commit atomically.
Audit events preserve the request ID. A second deterministic Signal UUID and
transaction lock bind hospital and aligned episode start, preventing a second
signal/audit for the same episode when model or delivery changes. Forecasts from
distinct input identities remain distinct. No R1 migration or shared UoW change
was needed.

## Protected reads and activation blockers

The parent integration exposes persisted evidence via
`GET /api/v1/forecasts/{UUID}` using ForecastQueryService and scope-filtered existing
forecast repository access. Organization evidence requires authorized canonical
hospital scope and current mapping; it does not fall back to global history.
The existing global persisted endpoint remains available for the initial UI.

Activation still needs owner-approved mappings and delivery coverage, independently
reviewed M3 sealed evidence/policy, an actual trusted registered model plus all
versioned/hash-bound evaluation/review objects, and compatible deployed runtime.
No production registration, owner approval, real model training, raw import or
service mutation was performed by R1. The flag remains false.

## Verification boundary

Synthetic unit/SQLAlchemy tests cover gates, artifact and runtime tampering,
provenance, seal contradictions, floors/equality, weekly offset/cadence, publication
revocation, protected input scope, rollback, operation states and episode dedup.
Global forecast and signal regressions are included. PostgreSQL integration tests
require explicit `R1_TEST_POSTGRES_DSN` targeting `phase8-*` (legacy `phase8_*` also
accepted), create a quoted `phase8-r1-<UUID>` schema and clean up only that schema.
They cover competing retries, atomic domain/audit rollback, state visibility and
competing watermark episode dedup. Without this isolated database they skip;
SQLite and in-memory tests do not establish live PostgreSQL race correctness.
