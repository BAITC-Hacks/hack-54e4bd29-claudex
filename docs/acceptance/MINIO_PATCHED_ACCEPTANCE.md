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

The only source changes are reviewed `go.mod` and `go.sum` patches, with SHA-256
values pinned in the build contract:

| Image | Direct security targets | Additional changes |
|---|---|---|
| server | `github.com/rabbitmq/amqp091-go v1.13.0`; `google.golang.org/grpc v1.79.3` | Required transitive module upgrades and Go directive `1.24.0` |
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

The CI browser job builds both patched images, records binary hashes and local
image IDs, generates CycloneDX SBOM and Trivy JSON, and checks Go/stdlib
inventory. **Any CRITICAL finding or missing Go inventory stops before Compose
startup.** HIGH findings remain security-admission failures; they do not become
suppressed. Only if the pre-start gate permits it does CI start the disposable
Compose stack, verify `minio-init` and scoped S3/MLflow operations, then run
the synthetic OIDC/browser journey. No failure is masked with
`continue-on-error`.

Run-scoped machine evidence is uploaded as `minio-source-build-evidence` and
`minio-source-runtime` on the Draft PR workflow. Record actual image IDs,
binary hashes, package versions, scanner DB date, HIGH/CRITICAL counts and
runtime results from those artifacts; do not infer them from this design.

## Current result: application security hold

The first patched CI run
[`36247311226`](https://github.com/zzhassyn/govtech_case1/actions/runs/36247311226)
was **cancelled during the source-build step, before scan or Compose startup**.
Its browser job is `108418778243`. No patched binary hashes or image IDs were
produced, the patched image scan did not run, and browser tests executed: **0**.
MinIO bootstrap, S3 policies, MLflow and OIDC/browser compatibility are all
**NOT TESTED**. The cancellation was deliberate after finding a CRITICAL
application-code advisory that dependency scanning may not surface.

The [upstream MinIO security advisory
GHSA-cwq8-g58r-32hg](https://github.com/minio/minio/security/advisories/GHSA-cwq8-g58r-32hg)
rates `CVE-2024-55949` **Critical**. It says the IAM import API allows
privilege escalation in releases before
`RELEASE.2024-12-13T22-19-12Z`; the selected server base
`RELEASE.2024-11-07T00-52-20Z` predates that fix. Our patches change only Go
module metadata and runtime OpenSSL packages, so they do **not** repair the
affected MinIO application code. The source-build helper now rejects this
known server commit **before cloning, building, scanning or starting images**;
preflight also refuses previously built image IDs. No bypass flag was added.

**FUNCTIONAL_ACCEPTANCE: BLOCKED / NOT TESTED. SECURITY_ADMISSION: FAIL.**
The original unmodified image scan still shows dependency CRITICAL findings.
The three existing backend, worker and MLflow image gates remain separate and
unmodified. The patched build's Go/OS vulnerability counts are **unknown**,
not zero.

## Decision needed

The approved dependency-only patch is insufficient. A separate decision is
needed before any new runtime attempt:

1. Select and authorize a newer, supported storage release/product for the
   isolated acceptance environment, then pin its source/image provenance and
   scan it, including known application advisories; or
2. Explicitly authorize a reviewed application-code backport of upstream fix
   commit `f246c9053f9603e610d98439799bdd2a6b293427` onto the exact 2024
   server tag **for synthetic acceptance only**, plus a wider advisory review.
   A backport would no longer be the unmodified upstream release.

Until one option is approved and verified, leave the gate closed. An isolated
synthetic environment does not turn this CRITICAL into production risk
acceptance.
