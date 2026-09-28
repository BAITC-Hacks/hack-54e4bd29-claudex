# Monitoring evaluation report — 2026-09-23

Experiment decision: **INSUFFICIENT_DATA — DEFERRED**.
Admission decision: **POLICY_NOT_APPROVED**, reason OWNER_ACCEPTANCE_REQUIRED.
No approved operational organization forecast/model is available from this work.

## What was actually done

Implemented the aggregate-only temporal harness, immutable protocol contracts,
episode metrics, cluster uncertainty and strict pure admission evaluator against
synthetic fixtures. Legacy Q1 pilot behavior is separately versioned legacy-q1-v1;
the new path is approved-aggregate-v2. No raw real data was accessed and no real
training, candidate selection, test evaluation or artifact replay was run.
No new unseen dataset or process-owner approval was provided. Tests are evidence
of software behavior, not of forecast utility, independent quality or approval.

The existing Q1 2025 period has already been inspected. Its earlier precision
42.86%, recall 4.05% and WAPE 84.286% are historical development evidence recorded
in the consolidation spec, not measurements produced or independently confirmed
by this change. No rerun of Q1 is claimed independent. Counts refer to recorded
referrals; there is no claim about patients, beds or clinical overload.

## Real-world gates still missing

- New, externally reviewed unseen period with a sealed access/history record.
- Owner-approved delivery semantics, reporting population and complete-day evidence.
- Approved canonical mappings with historical availability and verified projection.
- Process-owner numerical release thresholds, workload budget, sample-support minima
  and sign-off bound to the exact policy before test is opened.
- Train/validation comparison of weekly_naive, mean7 and existing HistGradientBoosting;
  validation-only selection; complete frozen provenance and parameter snapshots.
- Trusted versioned model artifact, matching SHA256/protocol, recorded final-test
  results and report integrity, then repeat inference reproducibility verification.
- Operational authorization, freshness, audit, persistence and shadow-pilot controls
  implemented/verified by integration owners; this ML report does not certify them.

## Provenance availability

| Item | Actual state |
| --- | --- |
| Baseline code | d965aff1665eeeff7e62d26be59beeef88324228; changes uncommitted |
| Real aggregate/dataset/source manifest hashes | Not supplied |
| Final train/validation/test dates and supplier timezone | Not approved/frozen |
| Mapping version and owner coverage review | Not supplied |
| Selected estimator/parameters/baseline | Not selected in a real experiment |
| Real frozen protocol SHA256 | Unavailable |
| Real model artifact SHA256 | Unavailable; no artifact created |
| Real sealed-period review | Unavailable |
| Numerical policy/sign-off | Draft only; not approved |
| Canonical decision | POLICY_NOT_APPROVED / OWNER_ACCEPTANCE_REQUIRED |

`ml/configs/monitoring_evaluation.json` preserves these missing fields as nulls
and cannot be frozen as a real protocol. Hashes/dates/approval records in
`tests/monitoring/admission-fixture.json` are deliberately synthetic. The immutable
protocol API requires full code, data, mapping, feature, estimator, dependency,
eligibility, label, split, baseline and uncertainty provenance when available.

## Technical verification

Commands run from the assigned worktree. Log directory:
`.superpowers/sdd/2026-09-23-03-model-evidence`.

- M1 RED: pilot-venv Python `-m pytest tests/monitoring/test_temporal_protocol.py -q`:
  8 failures on the missing contract/evaluation API (m1-red.log).
- M2 RED: pilot-venv Python `-m pytest tests/monitoring/test_alert_metrics.py
  tests/monitoring/test_admission.py -q`: 62 failures on missing episode/admission
  behavior (m2-red.log).
- Review RED: 5 failures for protocol not driving evaluation, predictor called on
  an incomplete target window, implicit estimator defaults, impossible empty
  support and numeric overflow (review-red.log).
- Provenance RED: 2 failures for unbound implementation digest and frozen eligibility
  being overridden by a default (protocol-red.log).
- GREEN: pilot-venv Python `-m pytest tests/monitoring -q`: 88 passed, one pre-existing
  Starlette/httpx deprecation warning (protocol-green.log).
- Existing ML baseline: `.venv/Scripts/python.exe -m pytest ml/tests -q`: 18 passed,
  one existing Pydantic protected-namespace warning (ml-baseline.log).
- Combined baseline in pilot-venv could not collect ml/tests/test_tracking.py because
  that intentionally isolated environment lacks mlflow. ML checks use .venv.

Final suite/lint verification and repository-wide environment limits are recorded
in the retained execution ledger; no commits or subagents were used. No dependency
or imports architecture changes were made. New imports stay inside ML or existing
standard/scientific libraries; neutral contracts do not import backend frameworks.

## Product consequence

Keep descriptive analytics and established rule-based data quality/freshness
behavior. Research replay remains explicitly historical/experimental. Neither a
synthetic PASS nor this report permits operational model-generated alerts.

Final verification (same implementation as decision fingerprint):
`.venv/Scripts/python.exe -m pytest tests/monitoring ml/tests -q` passed **106 tests**
with three existing dependency warnings (final-ml-monitoring.log).
Isolated pilot-venv `python -m pytest tests/monitoring -q` passed **88 tests**
with the existing Starlette warning (final-pilot.log). Configured Ruff check and
format check passed over all owned code/tests; git diff --check passed.
The root command `.venv/Scripts/python.exe -m pytest -q` stopped during collection:
`tests/pipeline: ModuleNotFoundError: No module named tests.pipeline` (full-suite.log).
That broader gate is not claimed green; no imports architecture was changed.

The executed draft decision and exact implementation file hashes are retained in
`MONITORING_EVALUATION_DECISION.json`. Decision SHA256:
`47ea352caeec54ddee3e23d1da9c20021b89549232adb1125eb62bd25185b913`.
Implementation SHA256:
`d2c566068f806bb34935ffb8b0ddfe850b4b14e9102854da681b9106ceaa2ad0`.
These identify code and a negative admission decision, not an approved model.
Self-review covered the plan's five review cases and trust boundaries; no subagent
or independent review was performed by this workstream.

## ML type-gate correction

The integration gate subsequently found 60 mypy errors in the four ML files.
They were reproduced with `.venv/Scripts/python.exe -m mypy ml --config-file
backend/pyproject.toml` (mypy-red.log), then corrected with explicit split arguments,
typed internal report/policy/uncertainty schemas after runtime validation, typed
predictor/collection annotations and explicit narrowing of optional observations.
The public admission dictionary interface, numerical rules, strict validation,
protocol behavior and existing tests are unchanged. No mypy configuration,
validation rule, adapter or dependency was weakened or modified.

Final correction verification:

- Exact mypy command above: **Success, no issues in 24 source files** (mypy-green.log).
- `.venv/Scripts/python.exe -m pytest tests/monitoring ml/tests -q`: **106 passed**,
  the same three dependency warnings (mypy-fix-tests.log).
- Ruff check and format --check for `ml tests/monitoring` using
  `backend/pyproject.toml`: passed, **28 files already formatted**.
- Whitespace verification of the four owned ML paths: passed.

The four updated file hashes and aggregate digest are recorded in
MONITORING_EVALUATION_DECISION.json. Current implementation SHA256:
`d2c566068f806bb34935ffb8b0ddfe850b4b14e9102854da681b9106ceaa2ad0`.
The negative decision SHA256 remains unchanged. Pascal/parent were notified for
R1 runtime hash binding; this work did not edit the adapter. No new model or
independent evaluation evidence was produced by this typing correction.
