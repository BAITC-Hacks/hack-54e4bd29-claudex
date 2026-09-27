# Aggregate analytics verification (U1-03B)

The read-only verifier calls five authenticated aggregate routes: overview,
daily referrals, daily refusals, waiting summary and the first organization
page. It checks a common period, import publication IDs, completion watermark
and mapping version; reconciles daily sums to overview counts; compares waiting
summary with overview; and validates bounded organization pagination. A
suppressed or missing cell is `NOT TESTED`, never zero. A failed HTTP response
is `FAIL` and its body is never written to the report.

Run only against an authorized synthetic or approved read-only environment:

```powershell
$env:PERFORMANCE_BEARER_TOKEN = '<test-token-from-authorized-realm>'
python -m scripts.performance.verify_analytics `
  --base-url http://127.0.0.1:<isolated-port> `
  --date-from 2025-01-01T00:00:00Z `
  --date-to 2025-03-31T23:59:59Z `
  --output tmp/acceptance/analytics-verified.json
```

The JSON report contains aggregate counts, publication metadata, source SHA and
a filter fingerprint. It excludes the bearer token, source organization values
and response bodies. For the same checkout and filter set, a benchmark can
refer to a `PASS` verification report with `--verification-report`; a mismatch
is rejected before traffic is generated. Without a report, benchmark results
are explicitly labelled `verification: NOT TESTED`.

Benchmarks record concurrency, total and successful requests, 429, 503,
timeouts, successful-only latency percentiles, cache state and declared dataset
size. Use separate cold/warm runs. These are engineering measurements, not an
operational SLA. **Real-scale verification is NOT TESTED** until the dataset and
path are explicitly authorized. Empty-store or synthetic timings must never be
reported as real-data performance.
