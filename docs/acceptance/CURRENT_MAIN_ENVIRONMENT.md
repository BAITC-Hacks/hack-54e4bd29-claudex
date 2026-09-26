# Isolated current-branch acceptance environment

This is a **local synthetic acceptance environment**, not production admission.
The image vulnerability gate is **FAIL**: backend, worker and MLflow each have
44 HIGH Debian OS findings in the current scan. Corporate SSO, public TLS,
DNS, firewall/VPN and real-data authorization are external dependencies.

## Isolation contract

`scripts/operations/prepare_acceptance.py` creates a fresh
`phase8-accept-<random>` Compose project. Its PostgreSQL, ClickHouse, Redis and
MinIO volumes are project-prefixed and new. Only nginx binds a host port, on
`127.0.0.1`. The project never touches the existing `medsignal` Compose
project or its volumes. A new random credential set and a derivative test
Keycloak realm live under ignored `tmp/acceptance/<project>/`; the supplied
local realm's fixed demonstration passwords and client secret are replaced.
No real medical dataset is mounted; the optional pipeline source mount points
to a new empty directory on read-only access.

The helper builds production image stages from the checkout, including a
Next.js build with the isolated loopback OIDC issuer. It captures exact local
content digests for backend, worker, MLflow, frontend, nginx and pipeline and
places those digests in the generated Compose overlay. `docker compose config`
is checked before startup for a matching project, project-specific volume
names and the absence of published data-service ports. The test Keycloak runs
in development mode only in this isolated project. `AUTH_TEST_MODE=false`;
browser and API checks must use real signed test tokens.

## Commands

From the repository root of the intended worktree:

```powershell
& .venv/Scripts/python.exe -m scripts.operations.prepare_acceptance prepare
# Copy the printed phase8-accept-* project name, then:
& .venv/Scripts/python.exe -m scripts.operations.prepare_acceptance start --project phase8-accept-XXXXXXXX
& .venv/Scripts/python.exe -m scripts.operations.prepare_acceptance verify --project phase8-accept-XXXXXXXX
```

Use an installed Python with the project's dependencies if `.venv` is absent.
The command does not print credentials. It records only digest, project,
synthetic-data and status metadata in `manifest.json`. Never attach `.env`,
`realm.json`, browser storage state, tokens, screenshots containing medical
data or unredacted Compose output to a PR. The project should be stopped and
its volumes removed only by explicitly targeting its exact `phase8-accept-*`
name after testing; do not use `docker compose down -v` without `--project-name`
and the acceptance overlay.

## Acceptance checks and current status

| Check | Status | Evidence required |
|---|---|---|
| Generated Compose structure, loopback port, new volume names | PASS | `tests/operations/test_acceptance_environment.py` and generated `docker compose config` check |
| PostgreSQL and ClickHouse migrations on fresh volumes | PASS | `phase8-accept-20260926a` one-shot `migrate` and `clickhouse-migrate` exited 0; services reached readiness |
| HTTP health/ready and Keycloak OIDC | PASS | `prepare_acceptance start` reached HTTP 200 for all three through loopback nginx |
| MinIO service identity bootstrap and effective access | PASS | `minio-init` exited 0; app, worker, pipeline and MLflow credential probes passed |
| Production Next build in isolated project | PASS | Production frontend image built and real browser journey completed in `phase8-accept-20260926d`; see `docs/frontend/USER_JOURNEY_AUDIT.md` |
| Real browser E2E and controlled HTTP 503 | PASS locally | Two journey tests passed with signed Keycloak identities; one separate dependency-outage test returned `/ready` 503, displayed a dashboard error and restored ClickHouse. CI job is added but has NOT TESTED runtime status. |
| Image security gate | FAIL | Current Trivy evidence in `docs/security/CURRENT_IMAGE_FINDINGS.md` |
| Real data, performance and production controls | NOT TESTED | Out of scope until explicitly approved |

The table must be updated from command evidence, never from configuration
presence alone. A local acceptance PASS does not override the image FAIL gate.

The first start attempt failed in `minio-init` because Git on Windows checked
out the bind-mounted `bootstrap.sh` with CRLF. `.gitattributes` now enforces LF
for all shell scripts, and a regression test checks their working-tree bytes.
The same namespaced project was then started successfully without deleting or
reusing another project's volumes. Exact image digests and successful probes
are recorded in ignored `tmp/acceptance/phase8-accept-20260926a/manifest.json`.
This run has no synthetic analytical facts yet; authenticated workflow and
browser tests remain separate pending checks.

A second fresh-project test of the later checkout found an MLflow restart
loop caused by a PostgreSQL driver mismatch. The Dockerfile now installs
`psycopg[binary]==3.2.*`, and the rebuilt image imported psycopg 3.2.13 and
MLflow 3.16.1. A **new** project, `phase8-accept-20260926c`, again reached
READY on fresh volumes; MLflow stayed running and its internal HTTP `/health`
returned 200. Three synthetic deliveries and an exact synthetic mapping
publication were verified there, as described in
`docs/acceptance/SYNTHETIC_ANALYTICS_RUNTIME.md`. Its image security gate
remains FAIL. The earlier `phase8-accept-20260926a/b` services were stopped;
their volumes were not deleted.

A third fresh project, `phase8-accept-20260926d`, used new volumes and the
corrected test-realm post-logout redirect. Three publishable synthetic datasets
and ten exact synthetic mappings were loaded. The browser covered login,
desktop/mobile routes, waiting snapshot, empty periods, human signal
acknowledge, scenario preview/save, restricted identity and logout. The
production frontend image was updated locally to test fast HTTP error handling
(content digest `sha256:3c906264d1acc298eacdbb7aacb034caffdd9467ca9536cb17b2d7250c2172e8`).
The controlled ClickHouse outage verified a real `/ready` 503 and frontend
error state; readiness returned after the `finally` restore. Docker Desktop
was restarted after its daemon stopped responding; no volumes were deleted.
