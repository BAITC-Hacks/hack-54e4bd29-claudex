# MedSignal Operator Runbook

## Назначение

Runbook описывает проверенные операции Compose-развёртывания. Он не заменяет
процедуры организации для DNS, TLS, firewall, VPN и корпоративного IdP.

## Запуск и состояние

Локальная демонстрация использует development realm и synthetic credentials:

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
curl -fsS http://localhost/api/v1/health
curl -fsS http://localhost/api/v1/ready
```

Production-конфигурация является overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.production.yml build
```

До production запуска оператор предоставляет external secrets, HTTPS issuer,
trusted hosts, CORS allowlist и подготовленный Keycloak/corporate IdP.
Development realm в production overlay не монтируется.

Публичный `/metrics` должен возвращать 404. Метрики читаются из private network:

```bash
docker compose exec backend curl -fsS http://127.0.0.1:8000/metrics/
```

В логах используйте `request_id`. Authorization, cookies, tokens и строки
медицинских выгрузок в логах появляться не должны.

## Миграции

```bash
docker compose run --rm migrate
docker compose run --rm clickhouse-migrate
docker compose run --rm backend alembic check
docker compose run --rm --entrypoint python pipeline -m app.cli.clickhouse status
```

Принятые Alembic revisions `0001–0006` и ClickHouse migrations `001–005` не
редактируются. Новое изменение схемы получает новую migration.

## Импорт

Источник задаётся снаружи и монтируется read-only:

```bash
make data-dry-run DATA_DIR=/approved/read-only/source
make data-import-core DATA_DIR=/approved/read-only/source
```

Повторный `dataset_type + SHA-256` возвращает `SKIP_IDEMPOTENT`. Успех — только
после публикации ClickHouse и `COMPLETED` в PostgreSQL. Не редактируйте source
files и не выводите строки источника в терминал или тикеты.

## Forecast, Signal и Scenario

```bash
make ml-train-referrals
make signal-evaluate
```

Q1 2025 forecast является историческим и временно устаревшим. Stale forecast
не создаёт operational growth signal. Stale source создаёт `DATA_STALE`, а
spike evaluators подавляются. Scenario — расчётный сценарий, не медицинская
рекомендация и не прогноз capacity.

## Диагностика

| Симптом | Проверка | Действие |
|---|---|---|
| API не готов | `/ready`, backend logs | Проверить PostgreSQL, ClickHouse, Redis и migrations |
| Ошибка авторизации | issuer/JWKS, Keycloak logs | Сверить public issuer и internal JWKS URL |
| Worker не принимает задачи | worker health, Redis | Выполнить `celery inspect ping` |
| Аналитика недоступна | ClickHouse status | Проверить migrations и imports |
| Import FAILED | DataImport/quality metadata | Исправить причину; не править facts вручную |
| Нет Signal | evaluator report | Проверить suppression, freshness и watermark |

Backup и restore: [BACKUP_RESTORE.md](BACKUP_RESTORE.md).
