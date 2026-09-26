# Project-built MinIO source images: security hold (2026-09-26)

**Functional acceptance: BLOCKED BEFORE STARTUP. Security admission: FAIL.**
This document records a synthetic-only build experiment in Draft PR #5. No
production image reference, existing volume, MinIO policy or vulnerability gate
was changed. Neither image was published to a registry.

## Reproducible build evidence

[CI run 36244948570](https://github.com/zzhassyn/govtech_case1/actions/runs/36244948570),
browser job `108412314092`, built both images on `linux/amd64` before any
Compose start. Machine-readable evidence, CycloneDX SBOMs and Trivy JSON are in
artifact `minio-source-build-evidence` (`10906534196`). The archive was a
shallow Git clone of the exact signed annotated tag, not a downloaded source
archive; `source_archive_checksum` is therefore not applicable.

| Component | Upstream tag | Signed tag-object SHA | Peeled commit SHA | Binary SHA-256 | Local Docker image ID |
|---|---|---|---|---|---|
| server | `RELEASE.2024-11-07T00-52-20Z` | `bae05edea0dee78128e59013583b80a8d971c74e` | `cefc43e4daa4cbb490ef6726ea374e26a93eb85e` | `7d4821181b6cb86a73f478cc9a70d5565190b8126b53de0022217f141b550502` | `sha256:8006eb84e6cc3fbbe2804458b66f75354df512be58ae63a442d7b1f2eaa7d55f` |
| client | `RELEASE.2024-11-05T11-29-45Z` | `653030740dcb89816d5320648a6b836a1a0d8e89` | `6ac18619cf881074fe6edcc79ab62c9c85da60b9` | `a5a6c20577bdda69c7cf0edb56234c4eaff2ab10c8abb49ef389c3dcdf950e0e` | `sha256:9a75dbd09364d568627974d976438f8fad734526d3d5107fb1234ba5064222a9` |

Both binaries reported the specified release tags. These are **project-built
images**, not official MinIO container releases. Their local Docker image IDs
are not registry manifest digests and are not asserted equal to the unavailable
official image digests.

The builder is Go `1.24.13` on `golang:1.24.13-alpine3.22@sha256:3641e0d9b931dc4f2f185dcd669c4679670e9277c8166a838ddb98a2d4389cb5`.
The runtime base is `alpine:3.22.2@sha256:4b7ce07002c69e8f3d704a9c5d6fd3053be500b7f1c69fc0d80990c2ad8dd412`.
The registry index manifests and `linux/amd64` entries were verified before
pinning. `go.mod` in each upstream repository specifies Go 1.22; the newer
builder compiled both with `GOTOOLCHAIN=local`, module checksums and readonly
module builds. Runtime packages installed by `apk` are not individually pinned;
the finished image scan below is authoritative for this run.

The annotated tags verified cryptographically with key fingerprint
`4405F3F0DDBA1B9E68A31D2512C74390F9AAC728`, obtained from the
`minio-trusted` GitHub account and checked against a pinned key-file SHA-256.
GPG reported a good signature but no independent local certification of the
key owner's identity. The upstream release page displays the server tag as
verified; this is supporting provenance, not proof of production admission.
No upstream binary checksum is claimed to match these locally compiled binaries.

## Final image scan

Pinned scanner: `aquasec/trivy:0.58.2` (image digest in machine report),
version `0.58.2`. The vulnerability database update time was **not captured**
in this run; the scanner invoked `--version` without its populated cache
volume. The local scanner helper now reads version metadata with the cache
mounted for a future run. The machine report's `vulnerability_database_updated_at`
remains `null`; it must not be retroactively filled in.

| Image | HIGH | CRITICAL | Detected Go components | Go stdlib detected |
|---|---:|---:|---:|---|
| server | 77 | 6 | 231 | yes |
| client | 64 | 3 | 100 | yes |

CRITICAL findings, with installed and scanner-reported fixed versions:

| Image | CVE | Package | Installed | Fixed | Scan class |
|---|---|---|---|---|---|
| both | `CVE-2026-31789` | `libcrypto3`, `libssl3` | `3.5.4-r0` | `3.5.6-r0` | Alpine OS packages; two package findings per image |
| server | `CVE-2026-77405`, `CVE-2026-77408`, `CVE-2026-77411` | `github.com/rabbitmq/amqp091-go` | `v1.10.0` | `1.13.0` | Go binary |
| both | `CVE-2026-33186` | `google.golang.org/grpc` | server `v1.66.2`, client `v1.67.1` | `1.79.3` | Go binary |

Counts are scanner findings, not distinct CVE counts: the OpenSSL CVE appears
once for each affected package. Package presence does not establish that every
vulnerable function is reachable in MedSignal, and no exploitability exception
has been approved. The approved rule requires stopping **before startup** for
any CRITICAL; the scanner exited 2. The three existing backend, worker and
MLflow image gates remain FAIL and were not modified.

## What was not run

Compose start, new-volume healthcheck, `minio-init`, bucket and service-account
bootstrap, positive and negative policy operations, S3/MLflow integration,
synthetic fixtures, OIDC and Playwright were all **NOT TESTED** in this CI run.
Browser tests executed: **0**. The runtime/policy verifier is implemented but
has not been run against these images; its CI step remains unreachable while
the CRITICAL gate blocks startup.

## Decision required before any runtime attempt

**Recommended separate authorization:** create a *patched acceptance-only
variant* that updates exactly `amqp091-go` to at least `1.13.0`, gRPC-Go to at
least `1.79.3`, and the runtime OpenSSL packages to fixed builds. This changes
the upstream dependency graph or runtime and is **not** an unmodified build of
the accepted 2024 releases. Pin and review the resulting module changes, rerun
Go module verification, builds and OS/Go/stdlib scans, then run the isolated
synthetic startup only if CRITICAL is zero and Go inventory is present. Document
remaining HIGH findings; security admission stays FAIL without a separate
review. Compatibility, especially gRPC-Go API behavior and MinIO bootstrap,
must be checked by the full existing synthetic acceptance path.

No dependency changes, runtime package upgrade, CRITICAL suppression, policy
relaxation or image startup is authorized by the current request. If the owner
does not approve the patched variant, leave functional acceptance blocked and
evaluate a separately approved storage release/product decision later.
