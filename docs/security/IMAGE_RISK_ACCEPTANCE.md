# Container image vulnerability admission

The latest local branch triage and its unresolved gate are recorded in
[CURRENT_IMAGE_FINDINGS.md](CURRENT_IMAGE_FINDINGS.md). The historical image IDs
below are retained as past evidence, not as approval of rebuilt images.

The `image-scan` CI matrix builds the current production stages for backend,
frontend and worker, builds the current MLflow image, and pulls the exact nginx
digest from Compose. Each image is exported to a temporary archive. Pinned
Trivy 0.58.2 (image digest
`sha256:665030f4d33a82c1e8d9d5e0453365842236723c1ee5cc3becca698268e66a56`)
scans that archive **without a Docker socket**. Its raw JSON, a
normalized JSON decision and a human-readable report are uploaded even when
the gate fails. A failed scan or unavailable vulnerability database is a
failure, never a clean result.

The gate **always fails on CRITICAL**. It also fails on every HIGH finding
unless [the acceptance manifest](image-risk-acceptance.json) contains an
unexpired, explicit security-owner decision covering that exact local image
content ID (`sha256:...`) and exact CVE/GHSA identifier. An acceptance entry
requires `image`, `image_id`, `vulnerability_ids`, `owner`,
`approval_reference`, `rationale`, and `expires_on` (ISO date). The exact
image ID comes from `docker image inspect`; it is the local image content
digest. Pulled images also report their registry manifest digest separately.
The finding remains in the machine and human report even when accepted.

The manifest is intentionally empty. **No existing HIGH is accepted by this
change.** Prior Phase 8 evidence recorded HIGH findings in the backend image,
but it is not a current-image scan and provides no approval for a rebuilt
digest. To admit an image with HIGH findings, a named security owner must
review the current raw report, document an explicit decision with an expiry
and ticket/reference, and commit the exact acceptance entry. Rebuilds change
the image ID and require rescan and fresh review. This gate does not claim
production admission or replace TLS, perimeter, identity, or runtime controls.
CI validates the record's shape and exact match, but cannot independently
authenticate the named approver; protected-branch review by the security owner
is required before merging any acceptance entry.

## Current local evidence (2026-09-24, not an acceptance)

Images were built from commit `c787184` with `docker build --pull` for the
production stages; nginx was pulled by the Compose digest. Finding counts are
package-level reports, while the CVE lists below are deduplicated. The exact
raw Trivy JSON and machine/human decisions are in ignored local
`artifacts/phase8-trivy-sidecar/<image>/` directories. CI will repeat the
build and scan and may produce different image IDs if upstream bases change.

| Image | Local content ID (`sha256:`) | HIGH | CRITICAL | Gate |
|---|---|---:|---:|---|
| backend | `293247fe9d1a65672456496413c1ea7ae5bd167825fd91269025fa7fb8126cf7` | 52 | 0 | FAIL |
| frontend | `9a42fccecc41738e79b7e3f4b559152cb53944665a43d32f507bc4e33a724363` | 0 | 0 | PASS |
| worker | `4f42c35b0cf81499162419e96fd2cfef1aeb5beb550e4034a13b60957c50dad2` | 44 | 0 | FAIL |
| mlflow | `484f13c218bde473c7492e43f72d221cbdaa3048be26d4ae6d6ed95fb8c7676e` | 44 | 0 | FAIL |
| nginx | `f2e97a6801f504129e8027ff7d49e27fa59ef4f1ebfd97197dac8b194831cf3d` | 1 | 0 | FAIL |

Backend unique IDs: `CVE-2025-69720`, `CVE-2026-12064`,
`CVE-2026-16742`, `CVE-2026-54369`, `CVE-2026-76642`,
`CVE-2026-78408`, `CVE-2026-78409`, `CVE-2026-78410`,
`CVE-2026-8286`, `CVE-2026-8458`, `CVE-2026-8927`,
`CVE-2026-9538`.

Worker and MLflow unique IDs: `CVE-2025-69720`, `CVE-2026-16742`,
`CVE-2026-54369`, `CVE-2026-76642`, `CVE-2026-78408`,
`CVE-2026-78409`, `CVE-2026-78410`, `CVE-2026-9538`.

The nginx finding is `CVE-2026-93990` in `libexpat` (`2.8.4-r0`);
Trivy reports fixed version `2.8.5-r0`. The targeted image build below
remediates it. The other HIGH findings had no fixed version reported by this
scanner database; that does not mean they are accepted or harmless.

## Nginx remediation in this branch (2026-09-25)

The pinned upstream Nginx digest is retained as the base in
`infrastructure/nginx/Dockerfile`; the image build installs exactly
`libexpat=2.8.5-r0`. `docker build --pull` produced local image ID
`sha256:a617a8595c0b2a0fa20d41c44fc416a084d681fd67ce3c0ad1bcbec57bc48e9f`.
Pinned Trivy 0.58.2 scanned **that built image** and reported **0 HIGH, 0
CRITICAL; gate PASS**. CI now builds and scans `medsignal-nginx:ci`, rather
than scanning the vulnerable upstream base. The earlier table records the
pre-fix scan and remains historical evidence. Backend/worker/MLflow HIGH
findings are still unresolved; no acceptance has been recorded. A future
base/package change must be rebuilt and rescanned before acceptance.

Example **synthetic schema only** (not an approval):

```json
{
  "acceptances": [
    {
      "image": "medsignal-backend:ci",
      "image_id": "sha256:<64 hex digits from this build>",
      "vulnerability_ids": ["CVE-2099-0001"],
      "owner": "<security owner>",
      "approval_reference": "<tracked decision>",
      "rationale": "<risk analysis and compensating controls>",
      "expires_on": "2099-12-31"
    }
  ]
}
```

For local verification, build the same images as the CI job and run
`python -m scripts.security.image_scan --image medsignal-backend:ci --output
artifacts/image-scan/backend.json`. The script creates the Trivy DB cache
volume `medsignal-ci-trivy-cache`; it does not delete unrelated Docker data.
On Windows, `scan-images.ps1 -Python <path-to-python.exe>` invokes the same
policy when Python is not on `PATH`.
