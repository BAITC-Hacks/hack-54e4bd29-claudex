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

## Current result

Pending the first patched CI run. The original unmodified image scan remains
**security admission FAIL** and **functional acceptance NOT TESTED**. The three
existing backend, worker and MLflow image security jobs are separate and remain
unmodified.
