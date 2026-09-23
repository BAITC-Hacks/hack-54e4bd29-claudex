# Pilot consolidation baseline

Date: 2026-09-23. Source baseline: ab620bc. Isolated branch: codex/pilot-reproducibility.
Scope: F1–F3 reproducibility package. This is not a new production acceptance or a real-data import.

## Environment

Windows host; Python 3.12.11; Node 24.14.1/npm 11.11.0 for native checks.
CI uses Node 22; the production Dockerfile also uses Node 22, checked separately below.
Docker Engine/CLI 29.2.1, Compose 5.0.2; pytest 8.3.5, Ruff 0.8.6, mypy 1.13.0.
Evidence logs are local ignored files under .superpowers/sdd/2026-09-23-01-reproducibility/.
No source medical files, database volumes or credentials were copied into the worktree.

## Baseline verification

| Check | Status | Observed result |
|---|---|---|
| Fresh frontend npm ci | PASS | 504 packages installed; npm audit reported 0 vulnerabilities at installation time |
| Frontend lint | PASS | ESLint exited 0 |
| Frontend typecheck | PASS | TypeScript exited 0; Leaflet resolves from existing lockfile |
| Frontend tests | PASS | 17 passed, 6 files |
| Native production build | PASS | Next.js 16.3.4 production build, all routes generated |
| Backend tests | PASS | 410 collected: 408 passed, 2 skipped |
| Root/data/security/operations/performance/E2E contracts + existing ML | PASS | 183 passed, 1 skipped |
| Backend Ruff | PASS | Four baseline I001 failures corrected by explicit monorepo package classification |
| Backend format | PASS | 195 files already formatted |
| Backend mypy | PASS | 146 source files |
| Import-linter | PASS | 12 kept, 0 broken; 252 files, 1245 dependencies |
| Base Compose config | PASS | Validated with .env.example; no environment values printed |
| Pilot Compose config | PASS | Validated successfully |
| Live database/token/restore acceptance | NOT TESTED | F1 did not launch or mutate current application services |
| Current medical-data counts/privacy-at-rest | NOT TESTED | No real-data queries in this package |

Backend integration skips require running services. The skipped root security test requires
real Keycloak identities. Contract tests passing does not replace those live controls.

## Commands executed

Run from repository root unless a directory is stated. PYTHONUTF8=1 and
PYTHONIOENCODING=utf-8 are set for Windows Python tooling; PYTHONPATH includes the
repository root and backend as appropriate. Native virtualenv executables were used.

~~~text
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r backend/requirements-dev.txt -r ml/requirements.txt -r data_pipeline/requirements.txt
docker compose --env-file .env.example config --quiet
docker compose -f docker-compose.pilot.yml config --quiet
# frontend working directory
npm.cmd ci
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
# backend working directory
../.venv/Scripts/python.exe -m pytest -q
../.venv/Scripts/python.exe -m ruff check .
../.venv/Scripts/python.exe -m ruff format --check .
../.venv/Scripts/python.exe -m mypy app
# root working directory
.venv/Scripts/python.exe -m pytest tests/audit tests/pipeline tests/security tests/operations tests/performance tests/e2e ml/tests -q
.venv/Scripts/lint-imports.exe --config .importlinter
~~~

## Root causes and corrections

1. Original checkout had stale/incomplete node_modules. Fresh npm ci fixed missing Leaflet;
   package.json/lockfile and TypeScript checks were not weakened.
2. Sandbox originally could not access Docker/runtime paths. The authorized isolated
   environment can access them; this was an environment failure, not a backend defect.
3. Backend and pilot pin incompatible Uvicorn versions. They are intentionally tested
   in separate environments; no dependency pin was relaxed to force one combined venv.
4. Import-linter needed UTF-8 on Windows to read Russian contract names.
5. Ruff classified sibling monorepo packages as third-party from backend cwd. Explicit
   known-first-party for app/data_pipeline/ml/pilot fixes four I001 errors without
   disabling a lint rule or moving business logic.

## Existing warnings and limits

Dependency warnings include deprecated third-party HTTP 422 naming/TestClient behavior,
MLflow/Pydantic namespace warning, and a deliberately invalid HMAC-key fixture warning.
No warning has been hidden by adding global filters. Native Node 24 results alone do not
prove Node 22 compatibility; container evidence is recorded after its build finishes.
Python requirements include version ranges: this check proves a successful current clean
resolution, not byte-identical resolution on all future dates.

Historical Phase 8 evidence remains dated 18.09.2026 and is not relabelled as a new check.
