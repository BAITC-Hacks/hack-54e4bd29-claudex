# Pilot release acceptance — 2026-09-23

**NOT ADMITTED. Frozen evidence/gate register; no signed admission.** R3-R5 were checked in the existing reproducibility worktree against the integration plan/spec. Source baseline d965aff plus concurrent uncommitted changes; parent performs final integration verification.

| Control | Status | Evidence / outstanding gate |
|---|---|---|
| Docker inventory | PASS | Server29.2.1; all10 current medsignal services remain running,7 healthchecks healthy. Does not establish executable runtime health. |
| Isolated configuration | PASS | `phase8-r-20260923`; generated ignored secrets; separate named volumes/networks; explicit free loopback-only ports validated. |
| Isolated clean deployment | NOT TESTED | PG/CH startup stalled; final project inventory showed no containers, volumes or networks. No changes to current services. |
| Node22 production frontend image | NOT TESTED | Build timed out180s at RUN steps; no build result. Minimal isolated node version probe timed out25s. F1 runtime gate stays open. |
| Monitoring test image | NOT TESTED | Build timed out90s at pip-install RUN; F1/F2 container execution gate stays open. |
| Native recovery/performance/infra tests | PASS |43passed in2.21s; Ruff check/format and diff whitespace check passed. Synthetic tests only. |
| PG clean and upgrade0007/0008 | NOT TESTED |0007/0008 and CH006 observed; no isolated database available. Final head must be coordinated with parent/D; accepted migrations unchanged. |
| Real signed-token roles/workflow | NOT TESTED |6ephemeral identities prepared, not imported or PG-seeded. All5roles plus scopedHA; ADMIN+globalHA reserved for ack race. Parent owns real test/E2E harness. |
| Restore content verifier source contract | PASS | Tests reject PG row/constraint/revision drift, CH migration checksum drift, MinIO same-size corruption/missing/extra objects, failed readback and unchecked manifest inputs. |
| Actual PG/CH/MinIO restore and workflow | NOT TESTED | No live backup/restore attempted against current stores; synthetic transport tests are not runtime evidence. |
| Real-data performance | NOT TESTED | Counts unknown after read-only timeout. See PERFORMANCE_RECHECK.md. |
| Live TLS/domain/certificate/proxy/firewall | EXTERNAL DEPENDENCY | Deployment owner/host/resources/domain/TLS issuer and trusted network boundaries not supplied. |
| Corporate IdP / SSO / PKCE perimeter | EXTERNAL DEPENDENCY | No approved real issuer/realm/client or browser/callback/logout/expiry evidence. Local generated realm is not corporate SSO. |
| Secrets provisioning / rotation | EXTERNAL DEPENDENCY | Random local secrets support isolated testing only; production ownership not supplied. |
| Backup destination / retention / RPO / RTO | EXTERNAL DEPENDENCY | Owner unknown; no numerical objectives invented. No achieved RPO/RTO measured. |
| Basic source/history secrets scan | PASS | Parent final scan returned no findings; see PILOT_CONSOLIDATION_IMPLEMENTATION.md. |
| Container image scanning and risk disposition | NOT TESTED | No fresh pinned-scanner run; no runtime image produced; no HIGH-finding owner/expiry acceptance inferred. |
| Operational alert exercises | NOT TESTED | HTTP/auth-status/latency, job and import/cache metric sources inspected only. No failure injection or verified alert delivery for import/stale/auth/latency/worker/model-quality classes. |
| Shadow observation and signature | EXTERNAL DEPENDENCY | Owner, duration, alert budget, eligible scope and signed decision absent. |
| Redis recovery as business truth | NOT APPLICABLE | Redis remains cache/broker/transport, not authoritative business state. |

## Recovery contract and limits

`backup.py` now records PostgreSQL public-table row counts, catalog constraint definitions/validation and Alembic revisions before/after the dump; ClickHouse migration version/checksum inventory; and MinIO object paths/sizes/SHA256. Writer quiescence is required: there is **no atomic cross-store snapshot**, and before/after counts cannot detect same-count content changes. This is not full PostgreSQL row-value hashing, roles/grants/index or application semantic verification.

`restore_verify.py` requires an explicit phase8-* project and namespace. Legacy backups remain inspectable but return `RESTORE_VERIFICATION_INCOMPLETE`, `restored=false`, exit2 when required evidence is absent; they are not silently upgraded. New evidence is checked before target writes, PG inventories are compared after restore, CH semantic aggregates/checksums are checked, and MinIO objects are read back from the destination and hashed. Any mismatch/command failure blocks success. Complete content verification returns `RESTORE_CONTENT_VERIFIED`, while application workflow remains NOT_TESTED and RPO/RTO acceptance remains EXTERNAL_DEPENDENCY. The SQL/runtime path still needs isolated live verification. No recovery PASS is claimed here.

## Resume conditions

Restore container execution without restarting/deleting current services or volumes unless separately authorized. Revalidate task-only resources/ports and secure ignored env, then coordinate PG0007/0008 and CH006 with parent/D. Seed synthetic subjects/scopes only in that instance, run clean+upgrade checks, parent real-role/race/refresh/retry workflows, and actual isolated content restore. Obtain external perimeter and owner inputs before final release review. Do not convert this report or local synthetic results into a signature.
