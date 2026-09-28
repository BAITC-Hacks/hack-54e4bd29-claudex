# D1–D3 implementation report — 2026-09-23

Worktree: medsignal-reproducibility/govtech_case1; baseline d965aff, branch codex/pilot-reproducibility. No commits, subagents, source-data reads/imports, or Docker service changes were performed by D.

## Delivered behavior

- New imports require an exact registered owner-reviewed manifest. Source/dataset periods are reserved under PG advisory locking; changed hashes cannot authorize overlap. Missing/extra parts, incorrect actual event periods, analytical row mismatch, rejected rows, unconfirmed snapshots and unsupported replacement block publication. Successful parts survive retry; published replay leaves audit/time unchanged.
- Mapping decisions use exact source roles, evidence, actor and optimistic alias version. Legacy ambiguous aliases cannot enter projections. Organization and region decisions/audit/generation commit together; revoked or newly changed mapping immediately invalidates active verification. CH candidates are verified by count and digest before PG activation and safely retried after lost insert acknowledgement.
- Every descriptive fact query uses a bound historical/published import allowlist and mapping version before scope and aggregation. Explicit effective global grant is required for unmapped/global views. Restricted queries reject an unavailable version and recheck PG before returning cached or queried results. Partial delivery counts appear only in explicitly marked global quality summaries; restricted quality omits all global exact totals.
- Freshness distinguishes event bounds, load/import times, confirmed date, cadence and PARTIAL state. Queue age is null until reviewed snapshot evidence exists and then uses only reviewed published waiting imports. TREATED load time is not treated as a reporting period. No model approval follows from freshness alone.

Stable reader interfaces, operator CLI, owner dependency table and runtime opt-ins are documented in [DATA_SUPPLY_CONTRACT](DATA_SUPPLY_CONTRACT.md). Mapping/cache/metric docs and [ADR-0019](../ADR/0019-versioned-mapping-projection.md) describe the decisions and restrictions.

## Evidence and remaining gates

| Check | Result |
|---|---|
| D native policy/service/repository/API suite | PASS: 148 passed, 2 runtime tests skipped |
| Typed touched application files | PASS: mypy29 files |
| D Python lint/format | PASS (see final logs) |
| Analytics component regressions | PASS: 5 tests, RED→GREEN, exit0 |
| Frontend scoped ESLint and full TypeScript check | PASS: both exit0 |
| Accepted PG0001–0006 and CH001–005 | Unchanged versus baseline; SHA-256 recorded |
| Offline SQL0006→0008 | Generated successfully; no live execution implied |
| Full clean offline SQL | BLOCKED at accepted0006 live scalar guard; unchanged |
| Real PG clean/upgrade/alembic check/concurrency | NOT TESTED: isolated runtime unavailable |
| Real CH migration/projection/query/equality | NOT TESTED: isolated runtime unavailable |
| Actual owner contracts/mappings/new data | EXTERNAL DEPENDENCY |

New revisions are `0007_delivery_manifest` and `0008_mapping_versions`; CH migration is `006_mapping_projection.sql`. CI clean and upgrade-to-head matrix is parent-owned. The opt-in PG/CH tests require explicit isolated environment and create only `phase8-d-<UUID>` resources; they were not run against current services.

Evidence directory: `.superpowers/sdd/2026-09-23-02-data-readiness/`. `progress.md` records RED/GREEN, scope decisions and reader contracts; `d-final-tests.log`, `mypy-final.log`, `ruff-final.log`, `format-final.log`, `frontend-final-*.log`, `migration-verification.log`, and `upgrade-0006-0008.sql` contain native/offline evidence. Other agents' simultaneous scenario/forecast RED tests are not D failures and were not modified here.

The author performed a separate self-review and regression pass. Parent-led independent review remains a separate gate. Native SQLite tests exercise real repositories/transactions with foreign keys and controlled CH fault injection; they do not prove PostgreSQL advisory locking or ClickHouse SQL execution. No production readiness or owner approval is claimed.

## Independent review corrections

Both findings in the independent D review were reproduced in eight native RED cases and corrected. Recovery now serializes with retry/publication, reloads after locking, refuses published/completed work, and keeps the lock through cleanup and status commit. Readiness rejects the entire damaged publication instead of certifying surviving parts; repeated publication also refuses damaged parts. Queue age uses the separate, defaulted snapshot-approved import ID list, preventing a reviewed snapshot from authorizing WAITING DELTA rows.

Focused post-review checks: **80 passed, 3 skipped** (`review-fixes-final-tests.log`); the three skips are opt-in PostgreSQL tests. Two new PG regressions verify both lock orderings using actual advisory-lock waiters when an isolated endpoint is supplied. They were **NOT TESTED live**. Application mypy passed on six changed files (`review-fixes-mypy.log`). Final scoped Ruff/format evidence is in `review-fixes-final-lint.log`. No migration changed. R1 was notified of the trailing defaulted DTO field and defensive readiness behavior. Parent-led re-review and isolated runtime validation remain separate gates.

Final parent integration: independent re-review closed both D findings with nine targeted regressions. Full backend:603 passed/10 live-service skips; full root+ML:325 passed/1 real-token skip. See [consolidation report](../acceptance/PILOT_CONSOLIDATION_IMPLEMENTATION.md) for the final verified scope. Live validation remains NOT TESTED.
