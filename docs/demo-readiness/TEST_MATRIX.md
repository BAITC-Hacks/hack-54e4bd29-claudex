# Demo readiness test matrix

## Проверяемая версия

- Код: `78ff9fffc0eaee2c01d4568e5b8b9adf84712ab4`.
- Ветка QA: `feature/demo-readiness-qa`.
- Среда: локальный одноразовый Compose project `phase8-demo-readiness-qa01`, origin `http://127.0.0.1:64243`.
- Manifest: `tmp/acceptance/phase8-demo-readiness-qa01/manifest.json` (локальный ignored-файл; `dataset=synthetic-only`, `git_sha=78ff9ff...`, status остался `PREPARED`).
- Данные: publication/bootstrap не выполнялся, потому что штатный `start` не достиг `READY`. Версия подготовленного генератора — `phase8-synthetic-fixture-v1`; фактически опубликованной версии данных в этой проверке нет.
- Evidence: только `sanitized-diagnostics.json` и вывод команд. Realm, credentials, tokens, cookies и storage state не сохранялись.

## Матрица

| Проверка | Тип данных | Шаги / команда | Статус | Safe evidence |
| --- | --- | --- | --- | --- |
| Exact source SHA и отдельная ветка | Код | `git rev-parse HEAD`, `git status --short --branch` | PASS | HEAD `78ff9ff...`, `feature/demo-readiness-qa` |
| Generated Compose isolation | Synthetic-only | Проверить project-prefixed volumes, bind sources, loopback port, отдельный realm | PASS | 4 volume с prefix `phase8-demo-readiness-qa01_`; 1 loopback port; 5 test identities; empty source dir |
| Acceptance prepare | Synthetic-only | `python -m scripts.operations.prepare_acceptance prepare --project phase8-demo-readiness-qa01` | PASS | Manifest status `PREPARED`, origin `127.0.0.1:64243` |
| Acceptance start | Synthetic-only | `python -m scripts.operations.prepare_acceptance start --project phase8-demo-readiness-qa01` | FAIL | `tmp/acceptance/phase8-demo-readiness-qa01/sanitized-diagnostics.json`; `clickhouse-migrate` exit 1 |
| First route: login → analytics → organization → signal → action → Copilot disabled | Synthetic-only | Browser route through real Keycloak/API | BLOCKED | P0 acceptance startup; nginx origin did not listen |
| New Playwright discovery | Test definitions | `npx playwright test e2e/demo-readiness --list` | PASS | 4 tests in 3 files, zero skipped in listing |
| New Playwright execution | Synthetic-only | `npx playwright test e2e/demo-readiness` | NOT TESTED | 4/4 stopped at the same environment precondition: `ECONNREFUSED /api/v1/ready`; no user step executed |
| Frontend unit suite | Synthetic unit fixtures | `npm test` | PASS | 18 files, 122 tests passed, 0 failed |
| Frontend typecheck | Code | `npm run typecheck` | PASS | Exit 0 |
| Frontend lint | Code | `npm run lint` | PASS | Exit 0, no diagnostics |
| Frontend production build | Code | `npm run build` | PASS | Next.js 16.3.4 compiled, typed and generated 12/12 static pages; exit 0 |
| Protected API without token and real Keycloak return path | Synthetic-only | `auth-and-scope.spec.ts` | NOT TESTED | Test discovered; runtime blocked before assertion |
| Hospital scope in list and direct URL | Synthetic-only | `auth-and-scope.spec.ts` with `admin` and `hospital-manager` | NOT TESTED | Test discovered; runtime blocked before login |
| Period affects analytics request and survives back navigation | Synthetic-only | `analytics-context.spec.ts` | NOT TESTED | Test discovered; runtime blocked before login |
| Region selection affects backend request and visible context | Synthetic-only | `analytics-context.spec.ts` | NOT TESTED | Test discovered; runtime blocked before login |
| Organization switch clears previous organization heading/context | Synthetic-only | `analytics-context.spec.ts` | NOT TESTED | Test discovered; runtime blocked before login |
| Forecast empty/published UI is explicit | Synthetic-only | Accept exactly one of unavailable state or labelled forecast chart | BLOCKED_BY_FORECAST_WORK | Browser execution blocked; forecast/MAE remains owned by the forecast agent |
| Fresh signal action, persistence and optimistic conflict | Synthetic-only | `signal-action-copilot.spec.ts`; requires fresh `NEW` + `SYNTHETIC_DEV_SEED` | NOT TESTED | Test discovered; bootstrap did not run |
| Real `COPILOT_DISABLED` keeps algorithmic explanation | Synthetic-only | Real POST through browser/backend, no fixture and no API key | NOT TESTED | Test discovered; no LLM call attempted |
| Copilot success fixture already present | Synthetic fixture only | Existing `frontend/e2e/copilot.spec.ts` | NOT RE-RUN | Existing fixture is not a live LLM result and is outside the blocked new run |
| Presentation wording review | Static code review | Landing redirect, command center, dashboard, header | FAIL | Exact strings listed in `BLOCKERS.md`; browser rendering not reached |

## Interpretation

`NOT TESTED` here never means PASS. The four browser tests were selected and started, but all stopped before the first user action because the isolated origin never reached `READY`. A PASS must be produced again on the exact integrated SHA after the acceptance P0 is closed. Changes from forecast or design invalidate this matrix until the affected checks are rerun.
