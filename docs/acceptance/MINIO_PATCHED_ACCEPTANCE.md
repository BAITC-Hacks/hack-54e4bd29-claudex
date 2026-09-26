# Patched MinIO images for isolated synthetic acceptance

The owner authorized a **separate patched acceptance-only variant** after the
unmodified source build reported CRITICAL vulnerabilities. This is a local
functional experiment in disposable `phase8-*` projects, not a replacement for
official MinIO images, production configuration, or production admission. The
base Compose file retains its official Quay references. No registry push,
production deployment, real medical data, existing volume, or security
allowlist is involved.

## Provenance and patch scope

Both images start from the exact signed annotated tags and peeled commits in
[`minio-source-build.json`](../../infrastructure/acceptance/minio-source-build.json).
The GPG check runs **before** the project applies its patch. The variant is
explicitly named `PATCHED_ACCEPTANCE` in the build evidence and labelled
`patched` in the image; the binary's upstream release string alone is not
evidence of an unmodified release.

The source changes are reviewed `go.mod`/`go.sum` patches **and**, for the
server only, the exact upstream IAM-import security fix. SHA-256 values and the
resulting source tree hash are pinned in the build contract. The separate
[advisory review](MINIO_BACKPORT_REVIEW_2026-09-26.md) records all 27 official
advisories and the remaining affected findings.

| Image | Direct security targets | Additional changes |
|---|---|---|
| server | `github.com/rabbitmq/amqp091-go v1.13.0`; `google.golang.org/grpc v1.79.3`; exact upstream `CVE-2024-55949` backport | Required transitive module upgrades and Go directive `1.24.0`; `cmd/admin-handlers-users.go` |
| client | `google.golang.org/grpc v1.79.3` | Required transitive module upgrades and Go directive `1.24.0` |

The runtime remains Alpine 3.22.2 at a pinned base digest. The patched build
upgrades `libcrypto3` and `libssl3` from the configured Alpine repository and
scans the **finished image**. Repository packages are not individually pinned,
so the final SBOM, image content ID, package versions and scanner result must
be retained for each run; a future rebuild can resolve newer packages. The
Go builder remains pinned to `1.24.13` and uses `GOTOOLCHAIN=local`, checksum
verification and a read-only module build. The patched source is **not** an
upstream-signed release binary. Its compatibility must be established by the
real bootstrap, S3 policy, MLflow and browser acceptance checks.

## Gate and run order

The CI browser job builds both patched images, checks the live official
advisory feed against the reviewed set, records binary hashes and local image
IDs, generates CycloneDX SBOM and Trivy JSON, and checks Go/stdlib inventory.
**Any CRITICAL finding, changed/unreviewed advisory, or missing Go inventory
stops before Compose startup.** A separate disposable no-port MinIO instance
then tests unauthorized IAM import for limited and service-account identities,
and authorized admin import. It is removed before the full Compose project.
HIGH findings remain security-admission failures; they are never suppressed.
Only if every pre-start gate permits it does CI start the disposable Compose
stack, verify `minio-init` and scoped S3/MLflow operations, then run the
synthetic OIDC/browser journey. No failure is masked with `continue-on-error`.

Run-scoped machine evidence is uploaded as `minio-source-build-evidence` and
`minio-source-runtime` on the Draft PR workflow. Record actual image IDs,
binary hashes, package versions, scanner DB date, HIGH/CRITICAL counts and
runtime results from those artifacts; do not infer them from this design.

## Earlier verification history

The first patched CI run
[`36247311226`](https://github.com/zzhassyn/govtech_case1/actions/runs/36247311226)
was **cancelled during the source-build step, before scan or Compose startup**.
Its browser job is `108418778243`. No patched binary hashes or image IDs were
produced, the patched image scan did not run, and browser tests executed: **0**.
MinIO bootstrap, S3 policies, MLflow and OIDC/browser compatibility are all
**NOT TESTED**. The cancellation was deliberate after finding a CRITICAL
application-code advisory that dependency scanning may not surface.

The [upstream advisory](https://github.com/minio/minio/security/advisories/GHSA-cwq8-g58r-32hg)
rates `CVE-2024-55949` Critical. The owner subsequently authorized the
**exact upstream fix commit** `f246c9053f9603e610d98439799bdd2a6b293427`
for isolated synthetic acceptance only. The source-build helper still rejects
the unmodified base. The patched variant must pass source-tree, advisory,
image-scan and IAM runtime gates before Compose. A pinned patch does not by
itself prove functional or security acceptance.

## IAM regression evidence

CI run [`36254020141`](https://github.com/zzhassyn/govtech_case1/actions/runs/36254020141)
localized the previous generic probe failure to `create_service_account`
(mc exit code 1). The probe had generated a 48-character secret for that
service account. The pinned MinIO server's
`auth.CreateNewCredentialsWithMetadata` enforces a 40-character maximum for
service-account secret keys. The acceptance probe now generates a 40-character
random secret; this is a test-harness correction, not a change to MinIO source,
permissions, or production configuration.

In CI run [`36254595904`](https://github.com/zzhassyn/govtech_case1/actions/runs/36254595904),
the disposable pre-Compose IAM probe recorded `DENIED` separately for the
limited user and its service account, `ALLOWED` for the authorized admin,
unchanged limited-user policy, and successful cleanup. The sanitized probe
summary preserves each assertion and any primary/cleanup failure separately;
it contains no credentials or archive content. This proves this particular
runtime regression on the patched acceptance image. It does not constitute
production security admission.

The same run continued to the full synthetic Compose start, which failed in
`runtime_verify` with Keycloak in `restarting` state. PostgreSQL and ClickHouse
migrations and `minio-init` had exited successfully; the MinIO service was
healthy. The sanitized startup diagnostic does **not** establish why Keycloak
restarted. S3/MLflow verification, signed-token browser checks and Playwright
were therefore **NOT TESTED** in this run. The IAM probe's PASS is independent
of this later acceptance failure; `FUNCTIONAL_ACCEPTANCE` was blocked in that run.

## Keycloak realm mount and completed synthetic journey

Run [`36257197947`](https://github.com/zzhassyn/govtech_case1/actions/runs/36257197947)
isolated the failure without rebuilding MedSignal images: the generated realm
was owned by Linux runner UID/GID `1001:1001`, mode `0600`, with no ACL. The
exact acceptance image `quay.io/keycloak/keycloak:26.0` ran as UID `1000`,
GID `0`, and could not read the read-only bind mount. Its isolated startup
exited `1`, was not OOM-killed, and had no automatic restart. This also
explains why a later Compose snapshot of Keycloak as merely `running` did not
prove that realm import had succeeded.

Acceptance startup now inspects the rendered Compose image and grants read
access **only** to its verified non-root UID through a POSIX ACL on the
generated `realm.json`. The host owner keeps access; `.env` remains `0600`.
The write policy for all other generated secrets is unchanged. Missing ACL
tooling or an unresolved/root image user stops acceptance before Compose.

In run [`36257739306`](https://github.com/zzhassyn/govtech_case1/actions/runs/36257739306),
the same Linux read-only mount changed from unreadable (`0600`, no ACL) to
readable by UID `1000` (`0640` ACL mask). An unrelated UID `20001` still
could not read it. An isolated Keycloak imported the realm, returned HTTP
`200` from OIDC discovery, and had zero restarts or OOM events. The full
Compose attempt stopped separately at `minio-init` exit `1`; no browser tests
ran in that attempt. Its sanitized diagnostic did not establish a cause for
that one-off MinIO bootstrap failure, and no MinIO code or policy was changed.

Run [`36258664151`](https://github.com/zzhassyn/govtech_case1/actions/runs/36258664151)
repeated the successful Keycloak preflight and completed the full isolated
synthetic acceptance: MinIO pre-start gates, Compose and scoped bootstrap,
invented fixtures, signed-token scope checks, production Next.js browser
journey, real ClickHouse HTTP `503` scenario, dependency recovery, and
namespaced teardown. Numeric browser artifacts recorded **2 passed / 0
failed** for the normal journey and **1 passed / 0 failed** for the degraded
journey. This is functional evidence for synthetic data, not production
readiness. The production backend, worker and MLflow image gates still fail.

**SECURITY_ADMISSION: FAIL** regardless of synthetic functional outcome; a
supported production storage path has not been selected. The existing
backend, worker and MLflow image gates remain separate and unmodified.
