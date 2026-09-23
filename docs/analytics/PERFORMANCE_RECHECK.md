# Performance recheck — 2026-09-23

**R3: NOT TESTED. No current latency or throughput claim.** This is a frozen gate report, not production SLA acceptance. Source baseline d965aff plus concurrent integration edits; historical import figures are not current runtime evidence.

| Requirement | Result | Evidence / next step |
|---|---|---|
| Fresh authorized real fact counts | NOT TESTED | First `SELECT count()` against existing ClickHouse via read-only exec timed out after 40s. Counts UNKNOWN, not zero. |
| Completed delivery watermark / active mapping version | NOT TESTED | No successful current aggregate/metadata read. |
| Cold / warm overview, timeseries and organization list | NOT TESTED | Existing `scripts/performance/benchmark.py` inspected; not run without verified nonempty facts and credentials. |
| 200 requests, concurrency 20, identical filters | NOT TESTED | Required for each comparable run; no synthetic substitutes. |
| Redis cache hit/miss, query log, connection wait | NOT TESTED | Command-line cache labels alone are not measurements. No cache cleared. |
| CPU/RAM/container resource context | NOT TESTED | Docker stats stalled; task-owned client cancelled. |
| Synthetic operations/performance/infrastructure contracts | PASS | 43 tests, 2.21s; includes recovery changes, not 43 performance tests. |

No imports, patient-value reads, original-source edits, Redis FLUSHALL, current service restarts, or analytical tuning were performed. Fresh SQL aggregate query used `readonly=1` and `max_execution_time=10`; host timeout was40s. Local evidence: ignored `artifacts/phase8-r-20260923/real-counts.json`.

When runtime is available, parent must authorize the existing imported-fact endpoint and credentials. Verify count totals with bounded read-only aggregates first. If any relevant dataset is empty, record its actual zero and **NO PERFORMANCE CLAIM**; do not import original data without parent coordination. For a nonempty dataset, use the existing runner with explicit `--dataset-size`, requests200/concurrency20, fixed date/scope filters, mapping version/watermark, errors/status counts and p50/p95/p99. Measure cold and warm separately and report measured cache hits; clear only a task-owned analytics prefix, never broker state. Capture a SQL/query-log/API/cache baseline before considering code or index changes.

Engineering proposals remain warm overview p95<500ms and uncached timeseries p95<1s; the historical organization-list p50=2332ms/p95=3127ms is only a reference requiring comparable facts, filters and hardware. None is an approved SLA or a result of this recheck. Benchmark code was not modified without profiling evidence.
