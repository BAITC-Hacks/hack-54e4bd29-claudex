# Current-branch analytics validation

Status on 2026-09-26: **NOT TESTED at real-data scale**. This branch contains
the C1 filter fix, the C2 waiting-snapshot contract and a synthetic-only
read-only verifier. No new acceptance deployment, real-data import,
authenticated real-data query, or benchmark was
performed here. The earlier [performance baseline](PERFORMANCE_RECHECK.md)
belongs to a different source revision and cannot establish this branch's
latency or correctness.

## Prepared verification

`scripts/performance/verify_analytics.py` makes exactly three authenticated
GET requests: overview, daily referral series, daily refusal series. It uses
identical date/region/organization parameters and requires the same published
import IDs, mapping version and period in all three responses. It compares
`REFERRALS_TOTAL` with the sum of daily referrals and `REFUSALS_TOTAL` with
the sum of daily refusals. A changed watermark, duplicate/out-of-range period
or mismatched sum is **FAIL**. Suppressed/unknown cells and the absence of
published imports are **NOT TESTED**, never zero or PASS. Output contains only
aggregate counts, publication metadata, filter counts and Git SHA; never the
bearer token or full API response bodies.

After the isolated acceptance environment is ready and use of its data is
approved, run from the repository root with a token supplied through an
environment variable:

```powershell
& <python> -m scripts.performance.verify_analytics `
  --base-url https://<approved-internal-host> `
  --date-from 2025-01-01T00:00:00Z `
  --date-to 2025-03-31T23:59:59.999Z `
  --output artifacts/analytics/current-branch-verification.json
```

`PERFORMANCE_BEARER_TOKEN` must already be set in the process environment;
the script never prints or saves it. Only loopback permits HTTP. Its response
size limit is 2 MB per endpoint and timeout is bounded to 1–30 seconds. The
output path above is ignored by Git.

The C2 snapshot selector is covered by a synthetic isolated ClickHouse test:
two published snapshots, one unpublished import, distinct hospital scopes,
and equality of waiting summary, overview and organization counts. This is
not evidence that the current real-data delivery has owner-confirmed snapshot
semantics. The U1-03 verifier still covers only referral/refusal totals; its
real-data run and the real-scale benchmark remain **NOT TESTED** until an
approved isolated stand is available. Real-scale
performance requires the same prepared stand, exact source/image SHA,
publication watermark, dataset size, scope, cache state, concurrency, request
count, status/error counts and successful-only p50/p95/p99. Use the existing
bounded `scripts/performance/benchmark.py` for latency, without changing the
edge rate limits or claiming a result when HTTP errors occur.
