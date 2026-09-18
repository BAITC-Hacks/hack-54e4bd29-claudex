# Phase 8 Acceptance Report

Дата: 18.09.2026. Baseline commit: `aca79d8daa0061c045be37bd4054cd4a6ba5a60c`.

Допустимые статусы: **PASS / FAIL / NOT TESTED / EXTERNAL DEPENDENCY / NOT APPLICABLE**.

## Deployment и migrations

| Проверка | Статус | Evidence |
|---|---|---|
| Base Compose local/demo workflow | PASS | 10 сервисов, health/ready 200 |
| Отдельный clean deployment | PASS | `phase8-clean`, новые named volumes |
| PostgreSQL clean migrations | PASS | `0001` → `0006`; clean `alembic check` |
| Existing DB upgrade/check | PASS | Upgrade head; no new operations |
| ClickHouse migrations | PASS | `001–005` auto-applied and listed |
| Accepted migrations immutable | PASS | Нет diff в `0001–0006` |
| ORM metadata drift | PASS | Clean/live checks; `0007` не создана |
| Production overlay config/build | PASS | Config validated, images built |
| Production overlay E2E launch | NOT TESTED | Нет production perimeter/IdP/secrets |
| Temporary acceptance cleanup | PASS | `phase8-clean` containers/volumes и Trivy cache удалены |
| TLS certificate и DNS | EXTERNAL DEPENDENCY | Инфраструктура не предоставлена |
| Firewall/WAF/VPN | EXTERNAL DEPENDENCY | Инфраструктура не предоставлена |
| Corporate SSO | EXTERNAL DEPENDENCY | Corporate IdP не подключён |

## Data и workflows

| Проверка | Статус | Evidence |
|---|---|---|
| Controlled read-only import | PASS | 11 files; exact facts 767130/765182/1508732/2196 |
| Source unchanged | PASS | 15 files, 2,177,380,780 bytes; SHA-256 unchanged |
| Import idempotency | PASS | Repeat: 11 × `SKIP_IDEMPOTENT` |
| Analytics aggregates | PASS | Daily sums equal referral/refusal facts |
| Forecast training | PASS | COMPLETED, 36.992 s |
| Signal evaluators | PASS | SIGNAL/NO_SIGNAL/SUPPRESSED/INSUFFICIENT_DATA |
| Signal deduplication | PASS | Same watermark: `SKIP_IDEMPOTENT` |
| Human workflow | PASS | Acknowledge → Incident → assign/close → Scenario → Audit |
| Safe reset contract | PASS | Only `phase8-*`; unsafe names rejected by tests |

## Security и privacy

| Проверка | Статус | Evidence |
|---|---|---|
| Real Keycloak tokens | PASS | HEALTH_AUTHORITY, REGION, HOSPITAL |
| IDOR isolation | PASS | Out-of-scope Hospital returned 404 |
| Published ports | PASS | Только nginx; data services private |
| Public metrics blocked | PASS | Public 404; internal 200 |
| Security headers | PASS | nosniff, frame deny, referrer, permissions, COOP |
| Sensitive logs | PASS | 0 token/header/raw-ID matches |
| Privacy at rest | PASS | Raw identifiers absent; HMAC keys validated |
| Secret scan | PASS | Gitleaks 8.30.1; history + 537 candidate files |
| Image scan | PASS | Trivy 0.58.2; 0 CRITICAL, 0 fixable HIGH |
| CSP | NOT APPLICABLE | Не добавлялась без Next.js/OIDC validation |
| Vendor process privileges | PASS | PG/CH/Redis/Keycloak drop privileges; nginx workers non-root |
| MinIO non-root | NOT TESTED | Vendor default root; unsafe override не применялся |

Unfixed HIGH: backend 52, worker 44, MLflow 44; frontend/nginx 0. Scanner
не предлагает fixed versions. Это MVP risk с обязательным periodic rescan.

## Backup/restore

| Проверка | Статус | Evidence |
|---|---|---|
| PostgreSQL restore | PASS | 21 tables |
| ClickHouse restore | PASS | Exact facts/aggregates, migrations, empty staging |
| MinIO restore | PASS | 8 namespaced buckets |
| Redis backup | NOT APPLICABLE | Redis не source of truth |
| RPO/RTO | NOT TESTED | Цели не определены владельцем инфраструктуры |

## Tests и quality gates

| Проверка | Статус | Результат |
|---|---|---|
| Backend pytest | PASS | 407 tests: 405 passed, 2 skipped |
| Root/data/security/operations pytest | PASS | 166 tests: 165 passed, 1 skipped |
| ML pytest | PASS | 18 passed |
| Frontend tests | PASS | 17 passed, 6 files |
| Frontend lint/typecheck/build | PASS | ESLint, TypeScript, production build |
| Ruff/mypy | PASS | backend, ML, pipeline, Phase 8 scripts |
| Import architecture | PASS | 12 kept, 0 broken |
| Real token acceptance | PASS | 1 scope/IDOR test |

Environment-gated tests были skipped в общем suite; real Keycloak test выполнен
отдельно и имеет PASS evidence.

## Performance

| Проверка | Статус | Результат |
|---|---|---|
| 20-user real-data benchmark | PASS | 200 req/endpoint, 0 errors, warm cache |
| Overview warm target | FAIL | p50 185 ms; p95 3,114 ms |
| Timeseries target | PASS | p50 307 ms; p95 402 ms |
| Organization list target | FAIL | p50 2,332 ms; требует оптимизации |
| Formal production SLA | NOT TESTED | SLA не утверждён |

PASS для benchmark означает выполненное измерение без request errors. FAIL
фиксирует превышение инженерной цели organization list.

## Evidence

- `artifacts/phase8-clean/backend-junit.xml`
- `artifacts/phase8-clean/root-junit.xml`
- `artifacts/phase8-clean/real-keycloak-junit.xml`
- `artifacts/phase8-clean/e2e-final.json`
- `artifacts/phase8-clean/real-data-analytics-final.json`
- `artifacts/phase8-clean/performance-application-warm.json`
- `artifacts/phase8-clean/background-jobs.json`
- `artifacts/phase8-clean/restore-real4.json`
- `artifacts/phase8-clean/source-fingerprints-after-import.json`
- `artifacts/phase8-clean/observability-final.json`
- `artifacts/phase8-security/image-scan-production-accepted.json`
- `artifacts/phase8-security/gitleaks-history-final.json`
- `artifacts/phase8-security/gitleaks-working-tree-final.json`
- `artifacts/phase8-security/log-redaction-final.json`
