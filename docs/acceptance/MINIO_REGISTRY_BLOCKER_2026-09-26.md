# MinIO registry blocker — Draft PR #5, 2026-09-26

**Status: BLOCKED.** This is a synthetic acceptance finding, not a production admission. No image reference, MinIO policy, credential, application behavior, migration, or vulnerability gate was changed.

## Reproduction on the GitHub runner

Evidence: [CI run 36242720980](https://github.com/zzhassyn/govtech_case1/actions/runs/36242720980), browser job `108406149770`, sanitized artifact `public-registry-probe` (`10905963228`). The probe ran **before** Node/Playwright installation and custom product image builds, on the same `ubuntu-latest` runner as browser acceptance. Docker daemon and context identities matched with the current and temporary empty client configs. Runner platform: `linux/amd64`. The temporary config did not change or remove `~/.docker` and did not change the daemon endpoint.

| Required service | Exact public reference | Current client pull | Empty client-config pull | Anonymous registry manifest | Manifest digest |
|---|---|---:|---:|---|---|
| `minio` | `quay.io/minio/minio:RELEASE.2024-11-07T00-52-20Z` | exit 1, `UNAUTHORIZED` | exit 1, `UNAUTHORIZED` | Bearer token obtained, final HTTP 401 `UNAUTHORIZED` | NOT AVAILABLE |
| `minio-init` | `quay.io/minio/mc:RELEASE.2024-11-05T11-29-45Z` | exit 1, `UNAUTHORIZED` | exit 1, `UNAUTHORIZED` | Bearer token obtained, final HTTP 401 `UNAUTHORIZED` | NOT AVAILABLE |
| `keycloak` | `quay.io/keycloak/keycloak:26.0` | exit 0 | exit 0 | HTTP 200; `linux/amd64` supported | `sha256:09a381c715ab0b111835b70f2905955274843a219c6f27efb348e4d9f4086858` |

The first HTTP 401 was a standard Bearer challenge and **was not** treated as denial. For both MinIO repositories, the final manifest request after the anonymous token response also returned 401. A clean client config did not change the Docker pull outcome. This excludes a local Docker credential-helper/config issue as the observed CI cause. The data do not establish why the registry denies anonymous manifest access or whether an authenticated distribution channel exists. No MinIO root/S3 credentials were requested or sent to the container registry.

The public Docker Hub tags API returned HTTP 404 for **both same-version tags** under the upstream `minio/minio` and `minio/mc` repositories in a separate read-only check. That check used a different network from the GitHub runner; no Docker Hub manifest digest or working same-version container copy was verified. Switching from Quay to Docker Hub would therefore be an unproven fix. No third-party mirror, `latest`, other version, or made-up digest was adopted.

The upstream [MinIO server release](https://github.com/minio/minio/releases/tag/RELEASE.2024-11-07T00-52-20Z) and [server archive](https://dl.min.io/server/minio/release/linux-amd64/archive/) still identify the exact server version. The [mc archive](https://dl.min.io/client/mc/release/linux-amd64/archive/) identifies the exact client version. The GitHub tag refs for both repositories returned HTTP 200, but source tags and archived binaries are **not** a verified container-image copy or a registry manifest digest. The upstream community repositories are archived; historical binaries and images may carry unpatched security findings.

## Acceptance consequence

The required-image gate failed before the normal Compose start. The browser job executed **zero** fixtures, OIDC/signed-token checks, Playwright tests, MinIO bootstrap/policy checks, MLflow integration tests, or recovery checks. None are PASS. The regular acceptance `start` still performs image checks and then `docker compose up --no-build -d` with existing dependency conditions; previous disposable volume/network/container and `compose create/down` probes have been removed from that normal path. No existing data volume was attached or reset during this registry probe.

The backend, worker and MLflow Trivy gates remain FAIL and were not suppressed. Successfully obtaining or building a MinIO image would not establish security PASS. Real production TLS, corporate SSO, real-data performance and operational admission remain outside this evidence.

## One decision requiring project ownership

**Proposed option for review: build two project-owned images from the exact upstream server and mc release tags**, only for isolated synthetic acceptance initially. Pin each upstream tag/commit and builder/runtime base by immutable digest, verify upstream release signatures or checksums, record source and resulting image digests, check the reported server and `mc` binary versions, scan OS **and Go/application dependencies**, and exercise a fresh disposable MinIO volume with the existing healthcheck, `minio-init`, bucket/service-identity policies (including denied operations), S3 client and MLflow, followed by an idempotent bootstrap retry. Keep current production references and existing volumes untouched until an explicit review decision.

This adds two controlled Docker builds, an acceptance-only image override and supply-chain/security evidence. It also transfers build provenance, rebuild and vulnerability maintenance to this project; the 2024 code may contain unfixed vulnerabilities, and compatibility with the current bootstrap is unproven. It is a substantive distribution choice, **not** a mere registry-host correction. Do not implement or publish these replacement images without the owner's decision. Do not present this option as production-ready.
