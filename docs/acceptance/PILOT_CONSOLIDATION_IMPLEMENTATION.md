# Pilot consolidation — D / M / R

> **2026-09-24 follow-up:** [Runtime recheck](PILOT_RUNTIME_ACCEPTANCE_2026-09-24.md) supersedes the historical runtime NOT TESTED rows below for completed container, migration, live-role and restore checks. Backend image findings and performance failures still block release. The following dated register is retained as historical evidence; operational admission remains unsigned.

Date: 2026-09-23. Branch: `codex/pilot-reproducibility`; baseline: `d965aff`.

**Operational release is not admitted.** This document separates implementation from runtime and external acceptance. No real datasets were read, imported, copied or sent externally during this change. Current application volumes and accepted PG0001–0006 / CH001–005 migrations were preserved.

## Implemented scope

- **D1–D3:** reviewed delivery manifests, exact part/hash/period/count validation, source reservation, publication visibility, versioned organization/region mappings, verified ClickHouse projection, immediate revocation and scope/cache checks. Unknown completeness/cadence/snapshot semantics remain unknown; legacy imports do not become operationally complete automatically. New PG0007/0008 and CH006 are additive.
- **M1–M2:** time-ordered, non-overlapping evaluation; frozen feature/episode/protocol provenance; baseline comparison, episode metrics, support/uncertainty, strict numerical admission policy. The historical pilot remains explicitly separate. **M3 has no real experiment:** independent data, owner policy, review evidence and an approved model artifact are absent.
- **R1:** default-off organization forecasting worker, existing PostgreSQL Forecast/ModelVersion/SystemOperation/Signal/Audit entities, trusted versioned artifact and evidence validation, publication/mapping gates, deterministic retry identity and transactional persistence. Enabling the flag alone does not authorize inference or signals.
- **R2:** authenticated `/monitor` and `/monitor/model?forecast_id=<UUID>`, scoped persisted forecast API, existing human Signal/Incident workflow, login return target preservation, identity-separated client cache and production exclusion of local research. Missing admission evidence is displayed as unavailable.
- **R3–R5:** measurable performance/release/shadow-pilot gate registers and stronger restore content verification. No timings, restore success, production perimeter or owner signatures are fabricated.

Restricted forecast and scenario evidence requires its saved mapping version to remain currently verified. This is intentionally conservative: an unrelated mapping publication can also hide older scoped evidence until reviewed. Global authorized historical review remains available. Scenario lists apply the mapping filter before SQL counting and pagination; revocation cannot disclose hidden totals. Global import quality totals are not returned to restricted roles.

## Integration corrections identified during review

- Published-file filtering now also covers legacy forecast history and metadata; changing publication during dataset preparation aborts persistence.
- Scenario baseline/read/retry paths enforce mapping revocation rather than bypassing the new forecast reader.
- Restore migration inventory uses ordinary MergeTree-compatible queries; destination object contents are hashed after readback.
- Login preserves the selected forecast UUID and cannot silently substitute latest GLOBAL evidence.
- Delivery recovery is serialized with publication and checks every manifest part; snapshot age uses only separately approved snapshot imports. Runtime code/dependency hashes and aligned weekly episode policy are checked before operational inference. Independent regressions confirmed these corrections.

## Verification

Final source checks: **PASS**, with explicitly skipped live-service tests. Runtime acceptance remains independent.

| Source check | Actual result |
|---|---|
| Full backend pytest | PASS: 603 passed, 10 skipped; exit 0. Skips require isolated live databases |
| Root security/pipeline/audit/operations + ML pytest | PASS: 325 passed, 1 skipped (real-token opt-in); 3 dependency warnings |
| Frontend Vitest | PASS: 79 tests / 10 files |
| Backend Ruff / format / mypy | PASS: 226 formatted Python files; 159 typed application files |
| ML Ruff / format / mypy | PASS: 28 formatted files; 24 typed source files |
| Import-linter | PASS: 12 kept, 0 broken; 272 files / 1465 dependencies |
| Frontend lint / TypeScript / production build | PASS: native Node24.14.1; Node22 container build remains NOT TESTED |
| Native production route smoke | PASS: four monitoring routes require login; root redirects to command center; pilot endpoint returns404; no production pilot rewrite |
| Compose base / production overlay syntax | PASS: both exit0; configuration validation only |
| Basic source + Git-history secrets scan | PASS: no findings; not equivalent to container vulnerability scanning |
| Accepted PG0001–0006 / CH001–005 | PASS: unchanged versus d965aff |
| New migration offline SQL0006→0008 | PASS: generated; live clean/upgrade is NOT TESTED |

Independent reviewers reproduced and then closed five concrete findings: recovery/publication races and damaged part completeness; mixed snapshot allowlists; model seal/split contradictions; actual runtime code/dependency binding; admitted alert-rule/cadence mismatch. Additional review corrected login return targets and unsupported MergeTree FINAL in restore inventory. Regression tests also cover scoped scenario revocation, SQL-before-pagination filtering, publication changes during global training and durable RUNNING/FAILED job state. Synthetic SQLAlchemy evidence does not prove PostgreSQL concurrency.

The initial backend invocation had an incorrect Windows PYTHONPATH and failed collection; the final full run above used explicit root and backend paths. An initial React test invocation with NODE_ENV=production was corrected by unsetting it for tests; production build remained a separate check. No application check was weakened.

| Gate | Status | Meaning |
|---|---|---|
| Real PG clean/upgrade/schema drift | NOT TESTED | Docker command execution stalled; no existing volumes were reset |
| Actual CH projection/aggregate equality | NOT TESTED | Opt-in isolated test provided; no live execution claimed |
| Real Keycloak identities / two-user race | NOT TESTED | Environment-only harness and synthetic validation exist; generated credentials remain ignored |
| Actual isolated PG/CH/MinIO restore | NOT TESTED | Source verification tests do not prove live recovery |
| Real-data latency / 20-user benchmark | NOT TESTED | No fresh counts/timing evidence; empty or synthetic timing is not substituted |
| Approved supply semantics / mappings / unseen evaluation data | EXTERNAL DEPENDENCY | Dataset/process owner review required |
| Production TLS / corporate SSO / network perimeter / RPO/RTO | EXTERNAL DEPENDENCY | Real infrastructure and owner decisions unavailable |
| Signed shadow-pilot admission | EXTERNAL DEPENDENCY | Protocol is a draft and observation has not started |

CI now has separate clean/from-0006 migration jobs and an isolated PostgreSQL/ClickHouse synthetic publication/race job. YAML validation is not a successful CI run. Full clean offline SQL remains unsupported by accepted migration0006's live emptiness check; that migration was not weakened. Offline generation of0006→0008 alone does not prove runtime migrations.

## Repeatable source checks

Run backend and root tests in separate processes: both trees contain a `tests` package. Include repository root and backend in PYTHONPATH. Do not run React tests with NODE_ENV=production; production build is a separate gate.

```text
# cwd backend, with repository root available on PYTHONPATH
python -m pytest tests -q
python -m ruff check .
python -m ruff format --check .
python -m mypy app

# cwd repository root
python -m pytest tests ml/tests -q
python -m mypy ml --config-file backend/pyproject.toml
lint-imports --config .importlinter
python scripts/security/scan_secrets.py --history
docker compose --env-file .env.example config --quiet

# cwd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Runtime tests require explicit isolated DSNs/ports and create only their own `phase8-*` namespaces. Do not point them at current application databases. Existing `make test` and `make lint` remain available when Docker execution is healthy.

## Review documents

- [Data readiness report](../data/DATA_READINESS_IMPLEMENTATION_REPORT.md), [supply contract](../data/DATA_SUPPLY_CONTRACT.md), [mapping ADR](../ADR/0019-versioned-mapping-projection.md).
- [Evaluation protocol](../ml/MONITORING_EVALUATION_PROTOCOL.md), [admission contract](../ml/MONITORING_ADMISSION_CONTRACT.md), [honest evaluation report](../ml/MONITORING_EVALUATION_REPORT.md), [machine-readable deferred decision](../ml/MONITORING_EVALUATION_DECISION.json).
- [Organization forecast integration](../ml/ORGANIZATION_FORECAST_INTEGRATION.md).
- [API](../API.md), [release acceptance](PILOT_RELEASE_ACCEPTANCE.md), [performance register](../analytics/PERFORMANCE_RECHECK.md), [shadow protocol](SHADOW_PILOT_PROTOCOL.md), [unsigned shadow report](SHADOW_PILOT_REPORT.md).

One task-owned Docker probe (`phase8-r-20260923-exec-probe`) may remain in Created state because its cleanup command timed out. No cleanup of user services or volumes was attempted.

Private local command logs and RED/GREEN review evidence are under `.superpowers/sdd/2026-09-23-*`; those ignored working artifacts are not a substitute for the tracked acceptance report.
