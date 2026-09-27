# TEAM_OWNERSHIP.md

## 1. Проверенная исходная точка

Дата проверки: **25.09.2026**.

Актуальный `main`:

```text
307339fcd4cddea6f5d4f0acd157da7e4053bf67
```

Последний коммит: `fix(ci): probe ClickHouse health over IPv4`.

Открытых PR на момент проверки нет. Недавно объединены:

| PR | Содержание |
|---|---|
| [#4](https://github.com/zzhassyn/govtech_case1/pull/4) | Hardening аналитики, инфраструктуры, хранения и проверок |
| [#3](https://github.com/zzhassyn/govtech_case1/pull/3) | Frontend |
| [#2](https://github.com/zzhassyn/govtech_case1/pull/2) | Обработка пустых агрегатов ClickHouse |
| [#1](https://github.com/zzhassyn/govtech_case1/pull/1) | Phase 8 production readiness |

Основной локальный каталог отстаёт от `origin/main` на **35 коммитов** и содержит незакоммиченные новые файлы. Для аудита использован существующий чистый checkout точного SHA. Перед разработкой нельзя выполнять `reset` или удалять локальные файлы ради синхронизации.

Последний [CI актуального SHA](https://github.com/zzhassyn/govtech_case1/actions/runs/36050773275):

- **14 jobs — SUCCESS**.
- **3 jobs — FAILURE:** сканирование образов backend, worker, MLflow.
- Сканер запускался и завершал анализ; ошибка возникла на vulnerability gate.
- Frontend build, backend/frontend tests, architecture checks и проверки миграций прошли в этом запуске.

Это сведения GitHub Actions. Локальный полный набор тестов в рамках данного аудита повторно не запускался.

## 2. Результат проверки старых замечаний

| Область | Классификация | Вывод |
|---|---|---|
| NaN и пустая аналитика | **Устаревшее замечание** | `_finite_float()` и регрессионные тесты уже существуют. Повторно исправлять не нужно. |
| Непубликованные/неуспешные импорты | **Старое замечание устранено в проверенном пути** | Есть фильтрация по опубликованным import IDs и интеграционный тест невидимости failed import. |
| Изоляция кэша | **Старое замечание устранено в проверенном пути** | Ключ включает scope, фильтры, mapping version/generation и import watermark; публикация перепроверяется после чтения. |
| Nginx rate limit | **Устаревшее замечание** | Реализованы 429, JSON error contract и Retry-After. |
| Производительность организаций | **Исправление без достаточной проверки** | Оптимизация существует; новый замер сделан на 30 синтетических referral facts. Работа на реальном масштабе актуального кода не доказана. |
| Backup/restore | **Частично закрыто** | В отчёте есть фактический synthetic restore трёх хранилищ и application readback. Production RPO/RTO и эксплуатационный режим не подтверждены. |
| Совместные region/organization filters | **Подтверждённая проблема по коду** | Наборы больниц объединяются вместо пересечения. Это ошибка фильтрации; обход SecurityContext этой проверкой не доказан. |
| Waiting KPI | **Подтверждённая проблема по коду** | Overview считает все подходящие опубликованные waiting rows, summary — последний snapshot. При нескольких снимках результаты могут расходиться. |
| Дата waiting snapshot в API | **Подтверждённый пробел контракта** | Repository получает дату, но публичный summary её не возвращает. |
| Навигация на узком экране | **Подтверждённая проблема по коду** | `hidden ... lg:flex`, альтернативного меню в компоненте нет. |
| HTTP 503 во frontend | **Подтверждённая проблема по коду** | Исключение для readiness применяется ко всем запросам, теряя исходный error contract. |
| Контейнеры | **Подтверждённый блокер CI** | Три image scan jobs красные. Точный список актуальных CVE ещё нужно классифицировать по scan artifacts. |
| Защита main | **Подтверждённый процессный пробел** | GitHub сообщает `protected=false`; список доступных repository rulesets пуст. |
| Операционный мониторинг | **Частичное исправление** | Метрики реализованы, но каталоги Prometheus/Grafana содержат только `.gitkeep`. |
| Браузерные E2E | **Пробел проверки** | Есть Vitest и Python workflow checks; воспроизводимого браузерного набора в проверенной конфигурации нет. |

Ключевые доказательства, на которые ссылаются задачи:

- **E1:** [analytics/service.py:188](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/backend/app/business/analytics/service.py#L188) — объединение фильтров.
- **E2:** [clickhouse_analytics.py:283](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/backend/app/repositories/clickhouse_analytics.py#L283), [тот же файл:444](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/backend/app/repositories/clickhouse_analytics.py#L444) — разные правила подсчёта waiting.
- **E3:** [schemas/analytics.py:84](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/backend/app/schemas/analytics.py#L84) — отсутствие snapshot metadata в summary.
- **E4:** [site-header.tsx:45](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/frontend/src/components/site-header.tsx#L45) — скрытая навигация.
- **E5:** [api-client.ts:108](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/frontend/src/services/api-client.ts#L108) — общий bypass для 503.
- **E6:** [ci.yml:381](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/.github/workflows/ci.yml#L381) — image gate.
- **E7:** [PERFORMANCE_RECHECK.md:3](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/docs/analytics/PERFORMANCE_RECHECK.md#L3) — ограничения свежих замеров.
- **E8:** [frontend/package.json:5](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/frontend/package.json#L5) — текущие frontend checks.
- **E9:** [PILOT_RESTORE_RECHECK.md:64](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/docs/acceptance/PILOT_RESTORE_RECHECK.md#L64) — фактически выполненный restore и его границы.
- **E10:** [PILOT_RELEASE_ACCEPTANCE.md:20](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/docs/acceptance/PILOT_RELEASE_ACCEPTANCE.md#L20) — внешние зависимости и незакрытая проверка alerts.
- **E11:** [waiting-age-summary.tsx:5](https://github.com/zzhassyn/govtech_case1/blob/307339fcd4cddea6f5d4f0acd157da7e4053bf67/frontend/src/features/analytics/components/waiting-age-summary.tsx#L5) — UI без конкретной даты снимка.

## 3. Границы проведённого аудита

**Просмотрены:** выбранные analytics routes/services/repositories/contracts, публикация импортов и mappings, cache keys, frontend transport/navigation/analytics types, прогнозные и scenario response contracts, Compose/migration startup, Nginx, image scanning, CI, состав тестов, отчёты производительности и восстановления.

**Не проверены полностью:**

- весь backend и каждая бизнес-ветка;
- все ML-алгоритмы и воспроизводимость их качества;
- актуальное содержимое реальных БД;
- каждый CVE из бинарных CI artifacts;
- реальный корпоративный IdP, TLS, DNS, firewall;
- браузерное поведение текущего SHA;
- фактическая доставка эксплуатационных alerts;
- полный набор эффективных прав production-среды.

Это **целевой аудит**, а не заявление о проверке всего проекта.

## 4. Люди и ответственность

| Участник | Ответственность |
|---|---|
| **У1** | Backend, API, бизнес-логика, БД, pipeline, ML, соответствующие тесты |
| **У2** | Контейнеры, инфраструктура, CI, сканирование, deployment, observability; координация merge и общего стенда |
| **У3** | Frontend, транспорт API, UX, браузерные E2E, пользовательский аудит и демо |

ИИ помогает исполнителю. Авторство решения, проверка результата и ревью остаются у людей.

## 5. Владение путями

Все пути ниже задаются относительно корня репозитория.

**Приоритет правил:** обязательное исключение → точное назначение файла → владелец каталога. Это даёт одного владельца каждому файлу.

| Путь | Владелец |
|---|---|
| `backend/**` | У1 |
| `data_pipeline/**`, `ml/**`, `pilot/**` | У1 |
| `database/**`, SQL-схемы и миграции | У1 |
| `data/**` | У1; реальные данные и закрытые artifacts не добавлять в Git |
| `frontend/**` | У3 |
| `infrastructure/**` | У2 |
| `.github/**`, `docker-compose*.yml`, `.env.example`, `Makefile` | У2 |
| `.dockerignore`, `.gitignore`, `.gitleaks.toml`, `README.md` | У2 |
| `.importlinter`, `ruff.toml`, `mypy.ini` | У1 |
| Остальные служебные файлы корня | У2, без автоматического разрешения их менять |

**Обязательные исключения:**

- Все `Dockerfile` и `*.Dockerfile` — **У2**, включая backend/frontend/pilot.
- Все Python dependency manifests — **У1**, независимо от каталога.
- SQL и миграции — **У1**, даже если расположены внутри infrastructure.
- Frontend types, Zod, `package.json`, `package-lock.json` — **У3**.
- Python pins, пока встроенные в MLflow Dockerfile, предлагает У1; сам Dockerfile редактирует У2. Предпочтительно отдельным согласованным изменением вынести pins в requirements-файл.

### Смешанный `tests/`

| Реальные файлы/группа | Владелец |
|---|---|
| Все текущие файлы `tests/audit/`, `tests/pipeline/`, `tests/monitoring/` | У1 |
| `tests/e2e/test_workflow_race_contract.py` | У1 |
| `tests/e2e/test_phase8_contract.py` | У2 |
| `tests/operations/test_backup_contract.py`, `test_postgres_roundtrip.py`, `test_restore_content.py` | У2 |
| `tests/performance/test_background_jobs.py` | У1 |
| `tests/performance/test_benchmark_statistics.py` | У2 |
| `tests/security/test_real_keycloak_roles.py` | У1 |
| `tests/security/test_acceptance_identities.py`, `test_compose_contract.py`, `test_container_versions.py`, `test_image_scan_policy.py`, `test_minio_least_privilege.py`, `test_nginx_log_contract.py`, `test_nginx_rate_limit.py`, `test_pilot_perimeter.py`, `test_secret_scanner.py` | У2 |
| Новый `frontend/e2e/**` | У3 |
| Остальные root test placeholders/package markers | У2 |

Backend tests остаются у У1, frontend component tests — у У3. Название `e2e` само по себе не определяет владельца: Python workflow harness и браузерные проверки — разные зоны.

### Смешанный `scripts/`

| Файлы | Владелец |
|---|---|
| `phase8_e2e.py`, `phase7-smoke.sh` | У1 |
| `performance/background_jobs.py`, `performance/benchmark_organization_query.py` | У1 |
| Новый `performance/verify_analytics.py` | У1 |
| `performance/benchmark.py` | У2 |
| Все текущие `operations/*.py`, `security/*.py`, `security/scan-images.ps1` | У2 |
| `demo/reset.py`, `demo/__init__.py` | У2 |
| `check-published-ports.py`, `dev-token.sh`, `smoke-test.sh` | У2 |
| Остальные служебные `__init__.py` в scripts | У2 |

### Смешанный `docs/`

По умолчанию владелец `docs/**` — **У2**. Исключения:

| Файлы/каталоги | Владелец |
|---|---|
| `docs/API.md`, `BUSINESS_LOGIC.md`, `DATABASE.md`, `DATA_ARCHITECTURE.md`, `ML_ARCHITECTURE.md` | У1 |
| `docs/SIGNAL_ENGINE.md`, `SCENARIO_ANALYSIS.md`, `MODEL_EXPERIMENT_PROTOCOL.md`, `MODEL_IMPROVEMENT_V2.md` | У1 |
| `docs/data/**`, `docs/ml/**`, `docs/analytics/**` | У1 |
| Исключение: `docs/analytics/SITUATION_CENTER.md` | У3 |
| `docs/acceptance/SHADOW_PILOT_PROTOCOL.md`, `SHADOW_PILOT_REPORT.md` | У1 |
| `docs/runbooks/DEMO.md` | У3 |
| Новые `docs/frontend/USER_JOURNEY_AUDIT.md`, `BROWSER_ACCEPTANCE.md` | У3 |
| `docs/ADR/**` | У1 |
| Исключения ADR: `0003`, `0004`, `0006`, `0009` | У2 |
| `TEAM_OWNERSHIP.md`, `INTEGRATION_CONTRACT.md`, `MERGE_PLAN.md`, `ACCEPTANCE_CHECKLIST.md` | У2 |
| `PERSON_1_TASKS.md`, `PERSON_2_TASKS.md`, `PERSON_3_TASKS.md` | Соответствующий участник |

Владение документом не означает право самостоятельно менять согласованный контракт. API-документацию редактирует У1, README и общий merge plan — У2.

---
