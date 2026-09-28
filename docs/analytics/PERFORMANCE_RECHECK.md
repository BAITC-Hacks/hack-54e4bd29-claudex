# Performance recheck — 2026-09-24

## 2026-09-25 branch probe — not a real-data comparison

The new organization repository was executed read-only from the current
worktree against the isolated `phase8-runtime-20260924` stack: 3 iterations,
latencies **94.22 / 55.38 / 54.40 ms**, median **55.38 ms**, first page 1 row,
total 1 organization, 1 published import. A separate read-only count proved
that this stack holds only **30 referral facts** and no waiting/refusal/treated
facts. These numbers are a small synthetic smoke measurement, **not** evidence
of a speedup at the real 3-million-row scale. The existing `medsignal` stack
contains the real facts but its PostgreSQL/ClickHouse schema predates delivery
and mapping publication. Migrating or rewriting its volumes merely to run a
benchmark was deliberately avoided. A comparable before/after real-data
benchmark remains **NOT TESTED**; run it after a controlled deployment/import
of the current migrations, with identical scope, watermark, date filters,
concurrency, cache state, success-only latencies and error accounting.

**R3: EXISTING DEPLOYMENT BASELINE RECORDED. NEW-BRANCH D/M/R ACCEPTANCE: NOT TESTED.** This is a bounded real-data baseline of the original `medsignal` development deployment, not production SLA acceptance. Every endpoint had errors under this workload. The mixed-status percentiles below do not establish successful-request latency targets.

## Deployment and data provenance

- Measurement window: `2026-09-24T11:19:39.899761+00:00` through `2026-09-24T11:23:17.131541+00:00` (UTC; local Asia/Qyzylorda is UTC+05:00).
- Running backend source: `C:/Users/zhasy/govtech_case1/backend` bind-mounted to `/app`, from `main` at `ab620bc383fce85759d15ff91ecb3104cab46e13`. Main tracked files were clean when captured; selected source/config SHA-256 hashes remained unchanged through final verification.
- Report/harness worktree: `C:/Users/zhasy/.codex/worktrees/medsignal-reproducibility/govtech_case1`, branch `codex/pilot-reproducibility`, HEAD `78d5f8ce8ae978b859f22543feaf464997210120`. This branch was **not** deployed for these measurements.
- Docker server: `29.8.0`. Container IDs, image IDs, mount sources, start times and limits for all ten original-project containers are in local `deployment.json`. Final verification found the same IDs, images and start times, all running; the measured backend process start timestamp was stable. A backend image Git revision label was absent, so the captured main mount revision is source provenance, not a claim about image build provenance.

| Component | Running image ID |
|---|---|
| backend | `sha256:e50ea7b2a9bed68101f338dd6722ac6ec63bde30c50cfb72b661f3461f8b67a5` |
| nginx | `sha256:f2e97a6801f504129e8027ff7d49e27fa59ef4f1ebfd97197dac8b194831cf3d` |
| clickhouse | `sha256:b002e56ed5c16e224c312527f6fcba7e77216fec5d7a88a7828f59efc614feb5` |
| redis | `sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499` |
| keycloak | `sha256:09a381c715ab0b111835b70f2905955274843a219c6f27efb348e4d9f4086858` |

Parent-verified read-only ClickHouse totals from `artifacts/phase8-runtime-20260924/existing-real-fact-counts.json` were reused; no table scan or import was performed by this task:

| Fact dataset | Rows |
|---|---:|
| Referrals | 767,130 |
| Waiting | 765,182 |
| Refusals | 1,508,732 |
| Treated snapshot | 2,196 |

These are whole-table dataset sizes, not separately counted Q1 result cardinalities. Successful overview/timeseries warmups reported completed-import watermark `2026-09-18T09:01:21.734209Z` and 11 latest import IDs; only the timestamp and count were retained. Active mapping version was not captured, so mapping-version equivalence with the new branch is unproven.

## Request contract and bounds

The client used `http://localhost` through the existing nginx gateway, with an ordinary OIDC password-grant login for the existing development-realm `admin`. Credentials were loaded internally from the main checkout's development realm JSON. No credentials, tokens, response bodies, organization names or patient values were saved.

All requests used `date_from=2025-01-01T00:00:00Z` and `date_to=2025-03-31T23:59:59.999Z`; region, organization and profile filters were omitted (normal authorized admin scope). Routes were `/api/v1/analytics/overview`, `/api/v1/analytics/referrals/timeseries`, `/api/v1/analytics/refusals/timeseries`, and `/api/v1/analytics/organizations`. Both timeseries used the deployed enum `granularity=DAY`; organizations used `page=1&page_size=20`.

Each valid run had one successful warmup followed by 200 measured requests in **ten sequential waves of 20 concurrent requests**. The ignored local wrapper called the unchanged `scripts/performance/benchmark.py` `_measure` and `summarize` functions. This wave scheduling is different from the CLI's single 200-request queue and must be matched in a comparison. Its CLI only accepts cold/warm labels, so the wrapper supplied the truthful `UNCONTROLLED` label directly; the tracked harness was not changed.

Client timeout was 5 seconds, with a 55-second deadline covering warmup, measurement and backoff; separate bounded private-metric reads surrounded each run. There were no request retries. After a wave containing HTTP 429 or 503, the wrapper waited at least 3 seconds before the next wave (or a longer numeric Retry-After). Overview, referrals and refusals each incurred 6 seconds of inter-wave backoff; organizations incurred none. No deadline was reached.

## Current results — existing main baseline only

| Endpoint | Requests / concurrency | Status counts | Error rate | p50 ms | p95 ms | p99 ms | Wall s* |
|---|---:|---|---:|---:|---:|---:|---:|
| overview | 200 / 20 | 200: 175, 503: 25 | 12.5% | 359.860 | 453.698 | 512.510 | 12.141 |
| referrals | 200 / 20 | 200: 187, 503: 13 | 6.5% | 472.465 | 807.842 | 844.279 | 11.640 |
| refusals | 200 / 20 | 200: 194, 503: 6 | 3% | 521.254 | 810.955 | 851.467 | 12.113 |
| organizations | 200 / 20 | 200: 176, NETWORK_ERROR: 24 | 12% | 3701.367 | 5070.053 | 5113.978 | 40.783 |

*Wall includes warmup and inter-wave backoff. Percentiles are the existing harness's nearest-rank statistics over all 200 measured outcomes, including HTTP errors and network failures; warmup and inter-wave backoff are excluded from latency samples. Successful-only percentiles were not captured. Warmup durations were 2219.053 ms (overview), 98.194 ms (referrals), 85.359 ms (refusals), and 271.859 ms (organizations).

The organization run's 24 `NETWORK_ERROR` outcomes are the harness's generic `httpx.HTTPError` classification. Their exact exception types were not retained; the approximately 5-second upper percentiles are affected by the configured client timeout and cannot be treated as completed-query latency. Aggregate backend counters registered 201 successful organization operations including warmup, consistent with server operations completing even where the client failed; they do not turn client failures into successes.

The active nginx configuration was captured read-only with `nginx -T`: API rate `20r/s`, `burst=40 nodelay`; auth rate `5r/s`, auth-route burst 20. No `limit_req_status` override was present. The 44 HTTP 503 responses are consistent with gateway limiting, but no per-response cause attribution was collected, so they remain HTTP 503 errors. No HTTP 429 was observed. Limits and service configuration were not changed.

An earlier **invalid referrals attempt** sent lowercase `granularity=day`: warmup 422, followed by 182 HTTP 422 and 18 HTTP 503 among 200 measured requests. This was a request-construction error, not a timeseries performance result. It is preserved separately as `invalid-day-referrals*.json` and excluded from the current table. The deployed enum was then verified as `DAY/WEEK`; the corrected valid run above was separate. Total analytics requests across this task were 1,005: 800 valid measured requests, four valid warmups, and the excluded 201-request invalid attempt.

## Cache and query evidence

**All runs: `UNCONTROLLED`.** No cache was cleared, expired deliberately or preconditioned beyond each initial warmup. The deployment's cache TTL environment value was `60` seconds. Before/after `/metrics/` reads occurred privately through `docker exec medsignal-backend-1` to backend loopback. Raw metric text was discarded; only numeric samples with strictly allowlisted labels were saved in ignored `*.metrics.private.json` and `*.metrics-delta.private.json`. No metrics route was published.

Derived deltas include the warmup and are observations of a shared process, not request-correlated traces:

| Run | Overview cache hits | Overview cache misses | Cache errors | Successful named analytics operations |
|---|---:|---:|---:|---:|
| overview | 175 | 1 | 0 | 1 |
| referrals | 0 | 0 | 0 | 188 |
| refusals | 0 | 0 | 0 | 195 |
| organizations | 0 | 0 | 0 | 201 |

Only overview uses the application's Redis aggregate cache in the inspected deployed main source. Zero overview-cache deltas on other routes do not prove cold database/OS caches. The overview interval observed one miss and 175 hits, but this does not establish a controlled cold/warm comparison. No matching backend HTTP-counter series was available in the selected private samples. SQL query-log aggregates and connection-wait measurements were not collected; named operation counters are not SQL query counts. Cache counter deltas cannot exclude unrelated concurrent activity.

## Resource context and limits on comparison

One `docker stats --no-stream` snapshot was captured at `2026-09-24T11:19:21.761758+00:00`, **before** benchmark traffic. It is resource context, not a peak-load or saturation measurement.

| Container | CPU snapshot | Memory usage / visible limit |
|---|---:|---|
| backend | 9.45% | 148.1MiB / 7.638GiB |
| clickhouse | 6.58% | 475.7MiB / 7.638GiB |
| redis | 0.96% | 8.016MiB / 7.638GiB |
| worker | 49.22% | 147MiB / 7.638GiB |
| mlflow | 2.58% | 1.9GiB / 7.638GiB |

Relevant original containers had no explicit Docker memory/CPU quota (`Memory=0`, `NanoCpus=0`). Other original services and the parent's isolated phase8 stack shared the host. These conditions are not an isolated hardware benchmark.

Engineering proposals remain overview warm p95 <500 ms and uncached timeseries p95 <1 s. Mixed outcomes, uncontrolled cache state and an old deployed revision prevent acceptance against those proposals. The historical organization p50=2332 ms / p95=3127 ms is not comparable proof of regression or improvement. No query optimization was attempted.

## Evidence and verification

Local ignored directory: `artifacts/phase8-runtime-20260924-performance/`. Files include `deployment.json`, `rate-limits.json`, `docker-stats-before.json`, one result JSON per endpoint, separate invalid-attempt records, private metric snapshots/deltas, `baseline_runner.py`, `finalize_baseline.py`, and `verification.json`. Private artifacts are not staged, uploaded or published.

Final verification checked all four valid 200-request totals, status/error arithmetic, concurrency, warmup success, deadline bounds, percentile ordering, matching dataset sizes, unchanged tracked harness and selected main source/config hashes, stable container identities/start times and backend process start, and absence of the loaded credential or access-token fields in JSON evidence. The result table is generated from those verified JSON files. No application or benchmark-harness code changed, so no new implementation tests were introduced.

No application data imports, manual database writes, auth bypass, user creation, cache resets/FLUSHALL, broker manipulation, service restart, parent isolated-stack changes, commits, pushes, subagents, raw dataset reads or external uploads were performed. Ordinary authenticated GETs can exercise existing application caching, logging and authentication session behavior. Parent-owned restore work remains separate.
