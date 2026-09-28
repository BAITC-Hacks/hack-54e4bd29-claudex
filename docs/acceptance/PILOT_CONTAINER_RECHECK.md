# Pilot container recheck - 2026-09-24

## Frontend security recheck

**PASS: patched frontend package, production smoke and scanner gates. Code frozen.** Source is `78d5f8ce8ae978b859f22543feaf464997210120` plus the three-line `frontend/Dockerfile` production-stage change: a comment, `RUN apk upgrade --no-cache`, and spacing. Dockerfile SHA-256: `0d4d79944e6e4f8cf7170c761defe02793dded488b1dcf2def97f17ca54570da`. No base major version, application dependency, CI policy, scanner suppression or authorization behavior changed.

Current local tags `phase8-runtime-20260924-frontend:production` and `phase8-runtime-20260924-frontend:latest` both resolve to `sha256:d5b3891bad5723083d7a4f63d1091014429f984eb729bf8894b2df3b254f324b`. The scanner analyzed an exported image archive whose config digest is `sha256:d5a854e215e99f5f63f4567a634ca7d714ed8e6e5914942d6bcaa9045c7ebd90`; its config digest and all layer DiffIDs were verified against the scan and current local image.

| Check | Before (RED) | After (GREEN) |
| --- | --- | --- |
| `libcrypto3` | 3.5.7-r0 | 3.5.8-r0 |
| `libssl3` | 3.5.7-r0 | 3.5.8-r0 |
| Runtime package floor >= 3.5.8-r0 | Exit 1, expected failure | Exit 0 |
| Scanner HIGH / CRITICAL | 2 / 0 | 0 / 0 |
| Scanner findings with a fixed version | 2 | 0 |
| All findings in independent unfiltered rescan | Initial parent scan recorded 2 HIGH | 0 across all severities |

The parent's initial report identified CVE-2026-14456 for both libraries, with fixed version 3.5.8-r0. The installed-version assertion reproduced the RED state in a task-owned, non-root, read-only, network-disabled container before the Dockerfile change. These are scanner findings and package observations, not proof of exploitability.

`apk upgrade --no-cache` used the existing Alpine v3.24 main/community repositories. Runtime `/etc/alpine-release` moved from 3.24.1 to 3.24.2. The same transaction updated libapk/apk-tools 3.0.6-r0 to 3.0.8-r0 and ca-certificates-bundle 20260611-r0 to 20260909-r0. Node remained 22.23.2, Next.js 16.3.4 and runtime UID 1001; npm remained absent. Production build passed in 46.85 s. The repeated HTTP/SSR smoke passed all four AuthGate routes, 12 referenced assets, root redirect, absent powered-by headers, absent pilot rewrite, and pilot-health 404.

The independent scan ran `aquasec/trivy:0.58.2` (verified version; image `sha256:665030f4d33a82c1e8d9d5e0453365842236723c1ee5cc3becca698268e66a56`) using cache volume `phase8-runtime-20260924-trivy-cache`. DB v2 was updated at 2026-09-24 09:10:28 UTC and downloaded by the parent at 11:16:21 UTC. The scanner container had no network and scanned an exported image archive, without mounting the Docker socket. Options were `image --skip-db-update --skip-java-db-update --offline-scan --scanners vuln --ignorefile /dev/null --format json --timeout 5m --input /evidence/frontend-image.tar`. No severity filter, ignore-unfixed flag, custom ignore entries or weakened CI gate was used. The scan exited 0 in 12.84 s; a separate assertion required zero findings with fixed versions and confirmed zero findings overall. Trivy inspected Alpine OS and Node.js packages. It labels the OS 3.24.1 and warns that branch 3.24 is missing from its EOL list; the independent runtime read reports 3.24.2 and unchanged v3.24 repositories. That scanner metadata limitation is retained in the raw log.

Evidence is under ignored `artifacts/phase8-runtime-20260924-build/security/`: `packages-red.json`, `packages-red-result.json`, `scan-red-summary.json`, `frontend-build-postrestart-security.log`, `packages-green.json`, `frontend-runtime.log`, `frontend-smoke-result.json`, `scanner-version.log`, `frontend-trivy-green.json`, `scan-green-summary.json`, `scan-green-result.json`, and `security-final-summary.json`. Initial parent findings remain at `artifacts/phase8-runtime-20260924/phase8-runtime-20260924-scan-1.json`.

All ten protected MedSignal services remain running with the same IDs and seven healthy checks. This task removed only its package-probe, smoke and scanner containers. It did not restart the parent's isolated frontend/nginx or any current service; running containers continue using their original image until the parent performs its authorized replacement. No real datasets, volume pruning, commits, pushes or subagents were used.

The parent's separate backend scan still records **52 HIGH, 0 CRITICAL, 0 fixable** findings in `image-scan-summary.json`. This frontend result does not clear those vendor-tracked OS findings or grant overall production acceptance. Existing TLS/SSO, real-token authorization and owner-approval boundaries remain unchanged. The earlier monitoring result (88 synthetic tests passed) remains historical evidence and was not rerun for this frontend-only OS patch.

## Initial container run (historical evidence)

Source: `codex/pilot-reproducibility`, `78d5f8ce8ae978b859f22543feaf464997210120`.

**PASS: bounded frontend production and synthetic monitoring container gate.** This report covers the post-restart run only; it does not establish full production acceptance.

## Verified results

| Check | Result | Evidence |
| --- | --- | --- |
| Docker client/server | PASS | 29.8.0 29.8.0; sandbox-elevated Docker access |
| Frontend production Docker build | PASS | Node 22 base; exit 0; 79.04 s |
| Production process | PASS | Node v22.23.2; Next.js 16.3.4; UID 1001; npm absent; pilot rewrite absent |
| Production HTTP/SSR smoke | PASS | Four monitoring URLs returned 200 with AuthGate; 12 referenced JS/CSS assets returned 200; powered-by header absent on monitoring pages |
| Production route behavior | PASS | `/` returned 307 to `/command-center`; `/api/pilot/health` returned 404 |
| Pilot development Docker build | PASS | Existing `pilot/Dockerfile` development target; exit 0; 223.54 s |
| Synthetic monitoring tests in container | PASS | 88 passed, zero failures/errors/skips; exit 0; 7.68 s command wall time |
| Monitoring runtime | PASS | Python 3.12.14; UID 1001; networking disabled |
| Protected service inventory | PASS | Same ten container IDs running before/after; same seven healthy checks |
| Task container cleanup | PASS | Frontend smoke and pilot test containers removed; images retained |

At initial verification these tags referred to the image below; the security recheck above supersedes this frontend image:

- `phase8-runtime-20260924-frontend:latest`
- `phase8-runtime-20260924-frontend:production`
- Image ID: `sha256:a5df667f3d07df0f48875b692081cd5d6020d323501a7365adc08b9ca32e65ad`

Monitoring tag: `phase8-runtime-20260924-monitoring:latest`.
Image ID: `sha256:bdf8ebcf522065643c2749211f47bb82bfba9863efd2b0b02fdd90774df2a501`.

## Reproduction and evidence

Builds ran sequentially with a 900 s overall cap and approximately 120 s without log growth. Neither build timed out. The frontend dependency installation used an existing cached layer; the production compilation and runtime checks executed successfully. This is not an uncached dependency reproducibility claim.

```powershell
docker build --progress=plain --target production --file frontend/Dockerfile --tag phase8-runtime-20260924-frontend --tag phase8-runtime-20260924-frontend:production frontend
python artifacts/phase8-runtime-20260924-build/container-checks.py frontend smoke-only
python artifacts/phase8-runtime-20260924-build/container-checks.py pilot
```

The pilot harness staged only 47 tracked files from `ml`, `pilot`, and `tests/monitoring`, preserving current bytes and recording their SHA-256 hashes. It built the existing Dockerfile using that staged context. No ignored artifacts, datasets or credentials were sent as pilot context. Monitoring uses synthetic fixtures and in-process FastAPI TestClient requests.

The frontend smoke used a task-owned container on an ephemeral loopback port, a read-only root filesystem, a temporary `/tmp`, UID 1001, 1 GiB memory, two CPUs, dropped capabilities and no-new-privileges. It used no host mounts or backend connection. Requests covered `/monitor`, `/monitor/model`, `/monitor/model?forecast_id=00000000-0000-4000-8000-000000000001`, `/monitor/synthetic-alias`, `/`, and `/api/pilot/health`.

The monitoring test container had no network, host mounts or published ports, UID 1001, 2 GiB memory, two CPUs, dropped capabilities and no-new-privileges. Its pytest invocation was `tests/monitoring -q -p no:cacheprovider --junitxml=/tmp/monitoring.xml`, after assertions for Python 3.12 and UID 1001. The JUnit file was copied out before removing the container. One Starlette TestClient/httpx deprecation warning was reported.

Ignored evidence directory: `artifacts/phase8-runtime-20260924-build/`.

- Build logs/results: `frontend-build-postrestart.*`, `pilot-build-postrestart.*` and corresponding `*-result.json` files.
- Runtime/smoke: `frontend-runtime.log`, `frontend-smoke-result.json`, `frontend-server-logs.log`.
- Monitoring: `pilot-tests.log`, `pilot-tests-result.json`, `container-monitoring.xml`, `pilot-source-manifest.json`.
- Inventory/cleanup: `protected-before-postrestart.log`, `protected-after-postrestart.log`, `frontend-remove-result.json`, `pilot-remove-result.json`, `owned-containers-final-postrestart.log`.
- Consolidated verification: `postrestart-summary.json` and `task-images-postrestart.log`.

## Earlier attempt and scope boundaries

The initial pre-restart frontend attempt was cancelled and its isolated Node probe timed out. Those initial logs remain for traceability and are superseded for this bounded gate by the successful post-restart container results. Previously recorded native checks were 79 frontend tests, a production build, native HTTP smoke, and 88 synthetic monitoring tests; they are separate historical evidence and were not rerun here.

For this initial container run, no Dockerfile, application source, requirement or test change was needed; the subsequent Dockerfile security patch is documented above. Only the acceptance report is intended for version control; execution helpers and raw logs remain ignored. This task did not restart, stop, exec into or remove any protected MedSignal service, use real datasets, prune volumes, create subagents, commit or push. It removed its two smoke/test containers and the leftover task-owned Node probe from the interrupted attempt, after confirming that probe was still Created with command `node --version`. Both images remain available for parent use. Probe inspection/removal evidence is in `previous-node-probe-*-postrestart*`.

AuthGate HTML is a UI observation, not a real-token backend authorization proof. Browser hydration, live identity-provider integration, database/service workflows, restores, model release admission and the parent's isolated nginx gate are outside this report. External TLS/SSO and owner approvals remain separate acceptance gates.
