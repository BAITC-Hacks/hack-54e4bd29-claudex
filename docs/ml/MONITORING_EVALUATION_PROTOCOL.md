# Monitoring evaluation protocol

Version: approved-aggregate-v2. Implementation baseline: d965aff; current work is
uncommitted by instruction. This is a technical evaluation protocol, not process
owner approval. The target is the count of recorded referrals at an approved
organization, not unique patients, bed availability or clinical overload.

## Input and compatibility

`ml.monitoring.train/aggregate/features/samples/predict/assess/alert_for` remain
legacy-q1-v1. Their three-file discovery, source-level names, 28-day reference,
partial-horizon training and pilot zero semantics are preserved. They cannot
supply independent admission evidence. Changing the code file changes its legacy
code-derived model ID; byte-identical historical report reproduction requires the
original source revision and trusted historical artifact. No legacy experiment
was rerun for this work.

The new path starts at `prepare_approved_experiment(rows, manifest, split)` or
`load_approved_aggregates(rows, AggregateManifest)`. No raw CSV discovery occurs.
Rows contain only organization_id (approved canonical ID), ISO day, and a
nonnegative integer value. Duplicate organization-days, unapproved organizations,
out-of-period rows and digest mismatches raise ValueError. This is a projection
of D's trusted approved delivery/mapping path; the ML layer does not approve it.

AggregateManifest binds schema, inclusive period, reporting population,
confirmed_complete_through, mapping version/availability date, mapping approval
reference, delivery evidence reference and canonical aggregate SHA256. Its
snapshot has a deterministic digest. Missing records become zero only inside
this approved population on supplier-confirmed complete days. Beyond the
watermark, even a partial positive count is UNKNOWN (None). The frozen dataclasses
keep completeness separate from value and prevent mutation of the series.

The supplying adapter must resolve/authenticate the mapping and delivery review
references and establish supplier-local day boundaries. Timestamp conversion
belongs upstream. The date-only evaluator accepts the supported protocol timezone
labels UTC, Asia/Qyzylorda and Asia/Almaty; it adds no timezone database dependency.
Missing mapping availability at the prediction origin prevents prediction.
Freshness is a separate operational concern and cannot repair invalid coverage.

## Temporal rules

SplitSpec requires train_end < validation_end < test_end and horizon_days=7.
An origin's *entire* seven-day target must end by train_end for training. There
are no shortened targets at the boundary. Validation begins the following day;
its last target ends by validation_end. Test starts after validation_end.
Only full, non-overlapping seven-day windows are scored; any trailing partial
window is outside evaluation support. Features require 28 complete preceding
days, ending at origin; they use the existing 12-feature direct-seven-day order.

Eligibility uses only complete training data and mappings available by train_end.
The frozen minimum_training_days/total drive the evaluator; future label changes
cannot enroll an organization. No future values enter features or baselines.
An incomplete history/outcome excludes the evaluation window with a reason and
INSUFFICIENT_DATA, never a substituted zero or forecast. Coverage must be complete
for admission; numerical metrics over surviving windows alone cannot promote.

`forecast_at(series, origin, predictor)` returns status and forecasts. Predictor
receives one 12-value row per organization/horizon and returns finite nonnegative
values. `walk_forward_score` uses that frozen predictor without fitting/refitting,
reports per-window MAE/WAPE and weekly_naive/mean7 comparisons, and records
excluded windows. `evaluate_protocol(rows, manifest, frozen_protocol, predictor,
partition='validation'|'test')` binds manifest/dataset/mapping digests, applies
frozen eligibility, and adds episode metrics and uncertainty. The caller controls
access to a sealed test; calling this pure evaluator does not establish that a
period was unseen or that an artifact/predictor is trusted.

## Immutable provenance

`freeze_protocol(payload)` requires every field in the protocol template in
`ml/configs/monitoring_evaluation.json`. Null template entries deliberately cannot
freeze: they await real provenance, not fabricated hashes. Required provenance:
aggregate manifest and dataset hashes, source manifest hashes, all split dates,
timezone, feature schema, mapping version, full code commit, implementation digest,
full estimator get_params() (including defaults), random seed, dependency versions,
training eligibility, label/reference policy, baseline selected on validation,
acceptance-policy version, uncertainty settings and known development periods.
Freeze all runtime dependency versions (including Python, NumPy, scikit-learn,
joblib, threadpoolctl and any artifact runtime used); the first three are enforced
by the boundary. The estimator parameters and seed are explicit; no favorable
fallback parameters are supplied.

The implementation digest is SHA256 of canonical JSON mapping each of
ml/monitoring.py, ml/monitoring_contracts.py, ml/evaluation/monitoring.py and
ml/evaluation/admission.py to its file SHA256. This distinguishes uncommitted code
from the baseline commit. Canonical JSON uses sorted keys, compact separators,
UTF-8, ensure_ascii=True and allow_nan=False. Array order remains significant;
source-row and source-manifest order must be retained by the producer. The
FrozenProtocol contains immutable canonical JSON; snapshot() returns a deep copy.
Its SHA256 changes with provenance. Persist canonical bytes immutably before
opening test, along with the separately hashed model artifact and approved policy.

Q1 2025 has been inspected and must remain recorded as development evidence.
The known-development list must also record every subsequently inspected period.
External reviewers attest independence and absence of test tuning; new timestamps
or newly computed dataset hashes cannot turn viewed data into a sealed holdout.
The protocol's baseline_selection must be weekly_naive or mean7, selected on
validation. Compare these with the existing HistGradientBoosting only on approved
train/validation data. No library or new medical feature is introduced.

## Episode quality and coordinator workload

An episode is an approved organization plus one aligned, non-overlapping seven-day
window. The label compares the outcome total with the mean of the four preceding
complete weeks (28 days): reference >=20, extra referrals >=10 and growth >=20%.
The reference ends at origin, strictly before the target. This is the existing
forecast-growth rule; it is distinct from the backend spike rule's eight preceding
reference windows, which is not changed here. WARNING/HIGH/CRITICAL remain
20/35/50%; operational freshness remains 72h/168h. A different rule needs a new
owner-approved version selected without viewing test.

Precision=TP/(TP+FP), recall=TP/(TP+FN), MAE=mean absolute error,
WAPE=100*sum absolute errors/sum actual. Zero denominators yield None, never
perfect quality. Alerts per organization-week=(TP+FP)/evaluated organization-weeks;
false alerts per organization-week=FP/the same denominator. Unknown outcomes or
predictions are excluded with an explicit count. Admission validates the complete
organization/window grid and coverage denominator separately.

The report includes TP/FP/FN/TN, support, lead time and false alarms/misses.
Lead time is window-start minus first issue date among true-positive episodes
with known issue dates; its support is explicit. It is not onset-of-overload lead
time. Daily replay additionally uses daily_alert_clusters: consecutive alert days
for one organization form one cluster. Daily alert volume and clusters are never
presented as independent weekly episode counts.

Uncertainty uses a fixed-seed crossed organization/week bootstrap: resample
organizations and seven-day time blocks independently, retaining all observations
in each sampled intersection. Percentile 95% intervals are reported for precision,
recall and false-alert workload with valid-resample counts. Fewer than two
organizations or four time blocks yields unavailable intervals with
TOO_FEW_INDEPENDENT_CLUSTERS. If fewer than 80% of resamples define a metric, its
interval is unavailable. These are technical support floors, not approved release
thresholds. Correlation beyond a week or across organizations can still make
intervals optimistic; a longer block rule needs a newly frozen protocol. Forecast
MAE/WAPE are point estimates here. Daily organization rows are not Bernoulli trials.

## Admission and external trust

See MONITORING_ADMISSION_CONTRACT.md and the single shared synthetic fixture at
`tests/monitoring/admission-fixture.json`. `evaluate_admission(report, policy)` is
pure and validates all keys/types/bounds, hash syntax, temporal evidence, count,
metric and workload support. Malformed input raises ValueError. It returns only
status, reason_codes and an independent policy_snapshot.

Decision precedence: POLICY_NOT_APPROVED for missing/unverified or mismatched
owner sign-off; INSUFFICIENT_DATA for absent independent/coverage evidence, viewed
Q1, seal binding failures, insufficient support or undefined quality metrics;
FAIL for any failed numeric threshold; otherwise PASS. All numeric policy gates
are required and conjunctive. MAE must be <= baseline MAE times the approved
max_forecast_error_vs_baseline. A zero-error baseline only permits zero model
error. Better MAE alone cannot establish alert quality.

External review records bind exact dataset/protocol/artifact/policy hashes and
attest unseen-before-open/no-test-tuning. Seal and freeze precede opening; opening
follows the complete test period. Coverage binds the same dataset, mapping and
period. Policy sign-off binds its complete canonical payload excluding sign_off.
Timestamps, approved booleans or independent_test flags alone are insufficient.
This function validates already-resolved records; it cannot authenticate a
reviewer, signature or object-store reference. R1 must independently fetch trusted
server records and verify their contents/digests, report integrity, exact artifact,
protocol and mappings. Never persist the synthetic fixture as approval or accept
client-supplied policy/evidence. Operational scopes, freshness, artifact loading,
versioning, persistence and audit remain R1 responsibilities.

## Deferred final experiment

No new unseen dataset or owner approval has been supplied. The checked-in config
is a blocked template and draft policy, not a frozen real experiment. No final
test has been opened and no model artifact has been trained or promoted. Once
external gates exist, freeze reviewed provenance, run one final evaluation, retain
per-window evidence and admission reasons, and repeat inference on the same
trusted artifact solely to check reproducibility. A tuned iteration after viewing
test needs new sealed data or an explicitly exploratory label.
