# MedSignal Integration and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Подключить допущенную модель к основному workflow и получить проверяемые основания для ограниченного эксплуатационного пилота.

**Architecture:** Reuse Forecast/ModelVersion/Signal/Incident/Action/Audit и существующие бизнес-сервисы. Основной OIDC/API обслуживает пользователей; pilot/api.py остаётся только localhost research. Deployment — существующий production overlay.

**Tech Stack:** Existing FastAPI/Keycloak, SQLAlchemy/PostgreSQL, ClickHouse, Redis/Celery,
Next.js/TanStack Query, Compose/Nginx, Prometheus/Grafana.

**Spec:** ../specs/2026-09-23-pilot-consolidation-design.md

## Global Constraints

Нет второго production backend и второго состояния сигналов в JSON.
GLOBAL и HOSPITAL scopes сохраняют смысл; mapped hospital не получается fuzzy matching.
STALE forecast не создаёт operational FORECAST_INFLOW_GROWTH.
Пороговые политики snapshot/version сохраняются в каждом Signal.
Training/bulk forecasts в worker, status в PostgreSQL.
Принятые migrations не менять. Новые только при действительном изменении схемы.
TLS/SSO/firewall и RPO/RTO не считать выполненными по наличию шаблона.

## Review Focus

1. Crash между persist и broker acknowledgement — R1 повтор не создаёт дублей.
2. Forecast структурно valid, но stale — R1 suppressed, historical UI marker.
3. Restricted OIDC identity открывает source/global URL — R2 404, no cache leakage.
4. Warm cache скрывает медленный cold path — R3 измеряет оба режима.
5. Restore завершился без проверки содержимого — R4 не выдаёт PASS.

## File map

| Файл | Назначение |
|---|---|
| backend/app/business/forecasting/contracts.py, ports.py, service.py | Organisation forecast integration |
| backend/app/adapters/forecasting.py | Adapter к допущенному ML artifact |
| backend/app/repositories/clickhouse_forecasting.py | Scoped approved aggregates |
| backend/app/repositories/forecast_metadata.py | Model admission/provenance |
| backend/app/business/signals/evaluation.py, evaluators.py, policy.py | Reuse signal engine и suppression |
| backend/app/repositories/signal_inputs.py | Evidence для global/canonical scopes |
| backend/app/api/v1/forecasts.py, schemas/forecasting.py | Authenticated aggregate responses |
| frontend/src/features/monitoring/ | Основной UI на authorized API |
| scripts/phase8_e2e.py, tests/security/test_real_keycloak_roles.py | Real-token workflow verification |
| scripts/performance/benchmark.py | Comparable benchmark evidence |
| docker-compose.production.yml, infrastructure/nginx/ | Production perimeter integration |
| scripts/operations/backup.py, restore_verify.py | Existing recovery path |

## Task R1: Подключить model output через существующие сервисы

**Depends on:** D1/D2 contracts and M2 admission. Technical implementation допустима
на synthetic fixtures при закрытом flag; operational activation требует M3 PASS.

**Files:** modify business/forecasting/{contracts,ports,service}.py,
adapters/forecasting.py, repositories/{clickhouse_forecasting,forecast_metadata}.py,
business/signals/{evaluation,evaluators,policy}.py, repositories/signal_inputs.py,
composition.py, adapters/composition.py, core/config.py; tests unit/test_forecast_service.py,
unit/test_signal_evaluation_service.py; new tests unit/test_organization_forecast.py.
При необходимости persist idempotency/admission fields создать
backend/alembic/versions/20260923_organization_forecast_evidence.py от actual head.

**Interfaces:** preserve existing ForecastEnginePort.train for GLOBAL reproduction.
Add optional OrganizationForecastPort in same ports module; proposed input:

~~~python
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from app.shared.forecasting import DailyReferralCount

@dataclass(frozen=True)
class OrganizationForecastInput:
    hospital_id: UUID
    mapping_version: str
    history: tuple[DailyReferralCount, ...]
    delivery_watermark: str
    as_of: datetime
~~~

Port method predict_organization(history: OrganizationForecastInput,
model_version: str) -> ForecastEngineResult.
ForecastEngineResult is existing contract; add optional admission evidence and
mapping version through explicitly versioned schema without breaking GLOBAL readers.

- [ ] Write tests: invalid/stale/insufficient model never fires operational forecast
  signal; valid CURRENT+admitted+mapped candidate can fire under existing threshold
  policy. Unmapped source receives no fake canonical hospital ID.
- [ ] Add config organization_forecast_enabled default false. Enabling flag is not
  sufficient: every job checks trusted artifact, admission, watermark, completeness,
  active mapping version and freshness.
- [ ] Read approved aggregates through repository; ML adapter sees no SecurityContext,
  raw patient rows, DB credentials or responsibility for actions/audit.
- [ ] Persist existing Forecast/ModelVersion with scope HOSPITAL, canonical hospital,
  points, selected/baseline metrics, training/evaluation periods, artifact/code hash,
  mapping/delivery versions, policy admission. Scope checks enforced in business layer.
- [ ] Reserve forecast job identity (hospital, target, origin, horizon, model version,
  mapping version, delivery watermark) in PG under unique constraint. Repeated worker
  reuses terminal result; failed attempt recoverable. Don't rely on Redis task result.
- [ ] Feed evidence into existing Signal Engine and dedup policy; no copied alert_for
  business rules in API/frontend. Existing eight complete non-overlapping reference
  windows tests remain; forecast rule and spike rule retain separate semantics.
- [ ] Fault tests after PG commit/before Celery ack: one Forecast job result and one
  Signal under same dedup key. Quality admission failure produces reason code,
  not model fallback falsely labelled ML success.
- [ ] Run forecast/signal unit tests, architecture checks and migrations clean/live;
  commit: feat: integrate admitted organization forecasts into existing services.

**Приёмка:** продемонстрировать safe negative path даже без новых данных; historical
STALE model остаётся доступна для review, но не для operational alerts.

## Task R2: Один защищённый human workflow и интерфейс

**Files:** modify api/v1/forecasts.py, schemas/forecasting.py,
frontend/src/features/monitoring/{api,types,monitor-page}.tsx/.ts,
frontend/src/app/monitor/page.tsx, frontend/src/app/monitor/[id]/page.tsx,
frontend/src/app/monitor/model/page.tsx, frontend/src/features/auth/auth-gate.tsx;
new frontend/src/features/monitoring/monitor-page.test.tsx;
modify tests/security/test_real_keycloak_roles.py, scripts/phase8_e2e.py;
new backend/tests/integration/test_monitoring_workflow.py.

Точная раскладка existing files: api.ts, types.ts, monitor-page.tsx.
Не создавать новый endpoint для статусов, если существующий Signal API покрывает операцию.

**Interfaces:** authenticated forecast read API uses canonical UUID, returns only
aggregate forecast/evidence. Статусы/assignment/acknowledge через existing Signal/
Incident API. UI explicitly separates historical research and operational evidence.

- [ ] Test frontend states with synthetic API responses: loading, no data, stale,
  admission rejected, scope denied, expired login, successful evidence view.
  Client does not compute authoritative rule thresholds or baseline.
- [ ] Replace production navigation calls to /api/pilot with existing authenticated
  services; local replay remains an explicit localhost-only mode controlled by
  build/config, without production replay mutations or automatic timers.
- [ ] Link forecast evidence → existing Signal detail → acknowledge → Incident.
  Assignment/status are human actions; model action suggestions never execute commands.
- [ ] Write API tests for ADMIN, scoped HEALTH_AUTHORITY, REGION, HOSPITAL_MANAGER,
  HOSPITAL_ANALYST: permissions+scope separately, outside scope 404, no source enumeration.
- [ ] Real Keycloak token E2E in isolated realm with ephemeral credentials via env.
  Verify global/source objects inaccessible to restricted scopes; verify two users
  racing status versions produce one success/one conflict and correct audit count.
- [ ] Exercise retry, refresh, server restart: persisted state survives; no JSON replay
  file participates. Assert SCENARIO remains immutable and no automatic incident from Save.
- [ ] Run frontend lint/types/tests/build plus integration/security tests;
  commit: feat: consolidate monitoring into authenticated human workflow.

**Приёмка:** один реальный пользовательский путь работает после перезапуска и не
зависит от unauthenticated pilot endpoints.

## Task R3: Измерить и исправить конкретные узкие места

**Files:** modify repositories/clickhouse_analytics.py, business/analytics/service.py,
scripts/performance/benchmark.py only after profiling; tests
backend/tests/integration/test_clickhouse_analytics.py,
backend/tests/unit/test_analytics_service.py, tests/performance/;
new docs/analytics/PERFORMANCE_RECHECK.md.

**Interfaces:** API schemas unchanged; cache identity includes filters, effective
scope, completed delivery watermark and mapping version from D3.

- [ ] Capture baseline on actual imported facts; verify SQL count totals before timing.
  Reuse benchmark runner, example command:

~~~bash
python -m scripts.performance.benchmark --base-url http://localhost --endpoint /api/v1/analytics/overview --requests 200 --concurrency 20 --cache-state warm --output artifacts/performance/overview-warm.json
~~~

Actual --dataset-size must be supplied from fresh count verification before the run;
do not use default empty size in acceptance. Keep endpoint date filters identical.
- [ ] Profile ClickHouse query_log + API timings + Redis hit/miss: distinguish SQL,
  repeated metadata work, count/pagination and connection wait. Don't tune guessing.
- [ ] Add equivalence regression on the identified query before change: same totals,
  filters, small-cell suppression, scope isolation and finite/null empty aggregates.
- [ ] Prefer existing daily aggregates and bounded query improvements. Add projection/
  index only when plan and query evidence justify it; versioned new DDL, no DROP facts.
  Never loosen filtering/privacy to reduce latency.
- [ ] Run cold and warm independently. Clear only task-owned analytics cache prefix,
  not FLUSHALL or broker DB. Record concurrency 20, requests 200 per endpoint, errors,
  p50/p95/p99, measured cache hits, dataset sizes, watermark, mapping version,
  CPU/RAM/container resources and query bounds.
- [ ] Engineering proposal: warm overview p95 <500ms, uncached timeseries p95 <1s;
  organization list improvement compared with recorded p50 2332ms/p95 3127ms.
  These targets are not promised production SLA. If missed, retain FAIL evidence.
- [ ] Commit: perf: optimize measured analytics bottleneck without changing scope semantics.

**Приёмка:** actual benchmark comparison; cache hit is measured, not inferred solely
from a command-line label; no timing claim from an empty database.

## Task R4: Production perimeter и recovery recheck

**Files:** modify docker-compose.production.yml, infrastructure/nginx/ configuration,
scripts/operations/{backup,restore_verify}.py only for demonstrated gaps;
tests/security/test_compose_contract.py, tests/operations/;
create docs/acceptance/PILOT_RELEASE_ACCEPTANCE.md.

**Interfaces:** existing production overlay, approved OIDC issuer/audience and TLS
gateway; backup contract includes PG/CH/MinIO integrity evidence, no Redis business state.

- [ ] Obtain infrastructure inputs: deployment host/resources, domain, TLS issuer,
  trusted proxy boundaries, network policy, real IdP realm/client, secrets provisioning,
  backup destination/retention and owner-selected RPO/RTO. Missing inputs are
  EXTERNAL DEPENDENCY; no demo users represented as corporate SSO.
- [ ] Launch separate Compose project with fresh volumes, namespace phase8-recheck,
  explicit free proxy port and matching local issuer. Do not run down -v against
  medsignal or reuse its volumes. Separate project name alone does not isolate ports.
- [ ] Verify clean PG/CH migrations, init, services, read-only controlled import,
  aggregate counts, privacy at rest, idempotency and workflow. Run upgrade test on
  restored isolated copy, never destructive rollback on current imported facts.
- [ ] At actual deployment perimeter test HTTPS redirects, certificate chain/expiry,
  OIDC callback/PKCE, issuer/audience, CORS allowlist, CSRF where applicable,
  logout/token expiry and normal browser flows. CSP only after Next.js/OIDC checks.
- [ ] Scan source/history/images with pinned scanner; save version, findings and
  exceptions. Document remaining unfixed HIGH vulnerabilities with owner/expiry;
  successful scanner execution alone is not risk acceptance.
- [ ] Re-run existing PG/CH/MinIO restore in phase8-* namespace. Verify row counts,
  constraints, migration checksums, object hashes and application workflow; measure
  actual RTO and achievable backup loss vs owner-approved RPO.
- [ ] Verify metrics/alerts for import failure, stale supply, auth failures, latency,
  worker failure and model-quality unavailability. Exercise one failure per class
  in isolated environment and confirm actionable operational signal.
- [ ] Record all controls with PASS/FAIL/NOT TESTED/EXTERNAL DEPENDENCY/NOT APPLICABLE;
  cleanup only verified phase8-* resources. Commit acceptance/config fixes.

**Приёмка:** live controls имеют live evidence. Recovery PASS требует восстановления
и сверки данных; отсутствие TLS/IdP остаётся blocker для соответствующего release.

## Task R5: Shadow pilot и решение о допуске

**Files:** create docs/acceptance/SHADOW_PILOT_PROTOCOL.md,
docs/acceptance/SHADOW_PILOT_REPORT.md; adjust existing operational dashboards only
when protocol reveals a missing metric.

**Interfaces:** consumes R1–R4 evidence and owner-approved duration/alert budget;
produces signed operational admission, limited scope and rollback criteria.

- [ ] С владельцем процесса выбрать организации, роль координатора, проверяемый
  action workflow, период наблюдения и response procedure. Не выдавать разработческий
  benchmark за SLA и прогноз роста за рекомендацию перераспределять пациентов.
- [ ] Запустить shadow mode: предупреждения проверяются людьми, автоматических
  медицинских/управленческих действий нет. Collect false alarms/missed episodes,
  подтверждение полноты поставок, время разбора и полезность explanations.
- [ ] Сравнить результат с замороженной M2 policy и baseline workflow.
  Редкие события или недостаточная длительность → INSUFFICIENT_DATA.
- [ ] Зафиксировать допуск владельца, ограничения и rollback: disable new model
  alerts, сохранить audit/history и descriptive analytics. Не удалять неудачные
  прогнозы для улучшения отчётности.
- [ ] Commit: docs: record shadow pilot admission decision.

**Приёмка:** конкретный владелец процесса принял измеренный результат; при отказе
работа остаётся полезным аналитическим пилотом с явно ограниченным ML.
