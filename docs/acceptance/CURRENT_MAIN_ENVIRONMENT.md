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
| PostgreSQL and ClickHouse migrations on fresh volumes | NOT TESTED | One-shot `migrate` and `clickhouse-migrate` exit 0 on an actual fresh project |
| HTTP health/ready and Keycloak OIDC | NOT TESTED | Loopback HTTP 200 from the actual project |
| MinIO service identity bootstrap and effective access | NOT TESTED | `minio-init` success plus scoped access probes |
| Production Next build in isolated project | NOT TESTED | Actual frontend image build and browser response |
| Image security gate | FAIL | Current Trivy evidence in `docs/security/CURRENT_IMAGE_FINDINGS.md` |
| Real data, performance and production controls | NOT TESTED | Out of scope until explicitly approved |

The table must be updated from command evidence, never from configuration
presence alone. A local acceptance PASS does not override the image FAIL gate.
