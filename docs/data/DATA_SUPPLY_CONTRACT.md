# Data supply contract — D1–D3

Status: implementation contract, 2026-09-23. **No owner answers or real approvals were received in this task.** All examples/tests are synthetic. Source directories remain read-only. Nothing has been sent to the data owner.

| Required owner decision/evidence | Status | Publication consequence |
|---|---|---|
| Source system, dataset and schema version | EXTERNAL DEPENDENCY | Must match the existing allowlisted pipeline |
| Cadence, cutoff time, source timezone and late-arrival policy | EXTERNAL DEPENDENCY | Unknown cadence never yields CURRENT |
| Event/reporting period; inclusive bounds and calendar semantics | EXTERNAL DEPENDENCY | No inferred dates; actual event bounds must fit the reviewed manifest |
| DELTA vs full snapshot vs correction/replacement | EXTERNAL DEPENDENCY | Overlap blocked; REPLACEMENT unsupported |
| WAITING snapshot timestamp meaning | EXTERNAL DEPENDENCY | No queue-age statistic until reviewed snapshot evidence matches facts |
| TREATED reporting period | EXTERNAL DEPENDENCY | Load timestamp is not event evidence; new publication fails closed |
| Independent exact file-part SHA-256 manifest and row totals | EXTERNAL DEPENDENCY | Missing/extra/duplicate parts or unconfirmed counts block publication |
| Stable source event keys and reconciliation rules | EXTERNAL DEPENDENCY | No deduplication by hospitalization_code or fuzzy reconciliation |
| Confirmed complete-through date, holidays/closures and zero-day evidence | EXTERNAL DEPENDENCY | Missing observations remain unknown; consumers cannot zero-fill |
| Baseline coverage of legacy imports | EXTERNAL DEPENDENCY | New period reservations for a source with legacy facts need explicit baseline review |
| Official organization/region code dictionaries with role and validity periods | EXTERNAL DEPENDENCY | No inferred mapping or scope entitlement |
| Official profile dictionary and canonical dimension | EXTERNAL DEPENDENCY | Profile mapping remains inactive |

## Review and import boundaries

An administrator explicitly reviews an exact `DeliveryManifest` using `DeliveryService.approve`; this stores its canonical digest, contract version, actor, evidence reference, expected parts, dates and cadence in PostgreSQL, with audit in the same transaction. File submission cannot approve itself. A CLI actor is an auditable operator subject on the existing trusted operator channel, not a new authentication mechanism. Evidence references must identify actual review material; a nonempty synthetic string is only valid in tests.

Only the four existing datasets are supported. A new non-dry-run import requires `--manifest` and a matching previously registered approval. Source/dataset advisory locking serializes reservation and overlap checks; all reserved periods block overlap, including incomplete deliveries. File hashes remain idempotency keys independent of filenames. A completed file cannot be rebound to another delivery.

Each file commits independently. Retry keeps successful parts and removes only unfinished import-owned analytical remnants through the existing recovery adapter. Partial results do not enter descriptive fact queries or operational readers; global quality may show explicitly marked PARTIAL counts. An approved manifest alone never certifies completeness: publication verifies all observed hashes/statuses, exact read/valid/loaded counts, zero rejected rows, analytical counts, actual event min/max or one exact snapshot date. Missing evidence blocks publication. A repeat of an intact already published manifest is a no-op, including audit and publication time. Recovery takes the same source/dataset transaction lock as retry/publication, reloads the import and delivery after acquiring it, and refuses completed imports or published deliveries before cleanup. The lock remains held through analytical rollback and the FAILED status commit. Readiness independently validates the complete manifest part set and counts: a damaged published delivery contributes no import IDs or complete-through date and yields PARTIAL with PUBLISHED_PARTS_INCOMPLETE.

Legacy imports retain NULL delivery linkage and remain visible historically. They never acquire a complete-through date or appear in operational published IDs merely because they were imported successfully.

Operator syntax (requires actual approved evidence; these commands were **not run** against source data):

```text
python -m app.cli.data approve-manifest --manifest <reviewed.json> --actor <operator-subject> --evidence-ref <owner-review-reference>
python -m app.cli.data --source <read-only-source> import --dataset REFERRALS --manifest <reviewed.json>
```

`--cadence-days` is optional and must come from the owner. `--legacy-complete-through` records explicitly reviewed historical coverage in audit and must precede the new period. It does not retroactively publish legacy facts operationally.

## Stable M/R read contract

`SqlAlchemyDeliveryRepository(session).readiness(dataset_type, source_system=None)` returns `DeliveryReadiness`: `published_import_ids`, `confirmed_complete_through: date | None`, `publication_watermark`, `completeness` (COMPLETE/PARTIAL/UNKNOWN), `cadence_days`, `snapshot_semantics_approved`, reason, and the trailing defaulted `snapshot_approved_import_ids: tuple[UUID, ...] = ()`. The general published IDs include intact DELTA and SNAPSHOT deliveries. Queue-age readers must intersect their allowed IDs with `snapshot_approved_import_ids`, which contains only intact publications with their own reviewed SNAPSHOT semantics; the boolean alone does not authorize general published IDs. An absent or empty snapshot ID list denies age computation. Operational consumers require COMPLETE, a suitable confirmed date, and their own daily-observation/eligibility gates. A confirmed date does not synthesize missing daily observations.

A source-specific consumer must acquire `lock_source(source_system, dataset_type)` and pass the same source to `readiness`, through final persistence. The lock key is the signed big-endian first 8 bytes of SHA-256 of `delivery:{source}:{dataset}`. For `SourceSystem.IS_BG`, the actual stored value is `ИС БГ`. If mapping and delivery locks are both needed, acquire mapping first.

`SqlAlchemyMappingRepository(session).lock()` serializes on PG advisory transaction lock 64730102. `readiness()` returns `MappingReadiness(version, generation, verified)`. Every approve/revoke invalidates verification until publication. Restricted saved evidence must compare its saved mapping version with the current verified version before and after reading, or hold the mapping lock through persistence.

`ClickHouseAnalyticsRepository.referral_timeseries(AnalyticsFilter(...), QueryScope(..., mapping_version=..., published_import_ids=...))` returns `RawTimeSeriesPoint(period_start, value)`. Operational callers must supply the delivery reader's published IDs, **not** historical analytics metadata IDs. Do not use legacy precomputed daily tables for this contract.

## Verification limits and migrations

New Alembic revisions: `0007_delivery_manifest` → `0008_mapping_versions`, starting at actual `0006_scenario_analysis`. New ClickHouse migration: `006_mapping_projection.sql`. Accepted PostgreSQL0001–0006 and CH001–005 are byte-equivalent to baseline d965aff after newline normalization (checksums in D migration log).

D upgrade SQL from0006 to0008 was generated offline. Full clean `--sql` stops at the accepted0006 live scalar emptiness check (`MockConnection` has no result); accepted history was not edited to bypass it. Actual clean/upgrade, `alembic check`, real PG locking, and CH DDL/query execution are NOT TESTED while isolated runtime is unavailable. CI has independent clean and from0006 upgrade jobs to head; preparation of those jobs is not evidence of a run.

Native SQLite tests enable foreign keys and exercise real service/repository transactions with synthetic projection fault injection. They do not establish PostgreSQL concurrency or ClickHouse SQL compatibility. Explicit isolated opt-ins: `D_TEST_ALLOW_ISOLATED=1`, `D_TEST_POSTGRES_DSN`, and `D_TEST_CLICKHOUSE_HOST/PORT/USER/PASSWORD`, running `backend/tests/integration/test_delivery_postgres.py` and `test_clickhouse_publication.py`. No default application connection is used. These tests create and clean only quoted `phase8-d-<UUID>` test-owned schema/database resources.
