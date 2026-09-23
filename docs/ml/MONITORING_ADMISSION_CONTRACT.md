# M2 / R1 shared admission contract

Import: `from ml.evaluation.admission import evaluate_admission`.
Signature: `evaluate_admission(report: dict[str, object], policy: dict[str, object]) -> dict[str, object]`.
Output keys exactly `status`, `reason_codes` (list[str]), `policy_snapshot` (deep copy).
Statuses: POLICY_NOT_APPROVED / INSUFFICIENT_DATA / FAIL / PASS. Malformed shape, unknown keys, invalid types/bounds, nonfinite numbers: ValueError. R1 must close on every non-PASS and on errors.

The complete minimal synthetic PASS-shaped fixture is `tests/monitoring/admission-fixture.json`. It is test data, never approval. No actual approved model or dataset exists. The draft call in the plan remains valid: report independent_test=false, coverage_complete=false; policy approved=false, version=draft-v1 yields POLICY_NOT_APPROVED / OWNER_ACCEPTANCE_REQUIRED.

Approved policies require every numeric field in the fixture and sign_off (null means absent). The policy SHA256 hashes the canonical JSON policy excluding sign_off, sorted keys, compact separators, UTF-8, no NaN. Precision/recall are fractions; WAPE is percent; max_forecast_error_vs_baseline is the maximum MAE ratio. Counts/support/budget denominators must agree.

Full reports require every fixture field; evidence may be null and then cannot PASS. Hashes are lowercase SHA256. External review records require review_status (VERIFIED_EXTERNAL or UNVERIFIED), reviewer_id, evidence_ref, evidence_sha256; no timestamp or boolean alone establishes approval or independence. Sealed evidence binds the dataset, immutable protocol, model artifact and policy digests. It must explicitly attest unseen_before_open and no_test_tuning, with ordered temporal splits and freeze/seal/open timestamps. Q1 2025 is development data and cannot be a new test. Coverage binds the same dataset/mapping and sealed test period with explicit expected/complete organization-days.

Trust boundary: the pure function validates evidence shape and consistency; it does not authenticate signatures or retrieve review records. R1 must load policy/report AND resolved external review records from trusted server persistence, verify that digests/references correspond to reviewed records and the loaded model/protocol, and never accept client evidence or let a caller self-assign VERIFIED_EXTERNAL. No real-world approval can be inferred from this fixture. The adapter returns a decision; it does not persist, load models or authorize scopes.
