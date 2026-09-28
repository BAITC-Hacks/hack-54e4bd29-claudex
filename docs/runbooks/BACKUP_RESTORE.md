# Backup and Restore Runbook

## Авторитетные stores

PostgreSQL хранит domain/operation state, ClickHouse — facts/aggregates, MinIO —
raw/quarantine/quality/artifacts zones. Redis не бэкапится: это cache, broker,
rate-limit и task-result transport, а не source of truth.

## Backup

```bash
PHASE8_BACKUP_DIR=./artifacts/phase8-backup make backup
```

Создаются PostgreSQL custom dump, ClickHouse DDL/Native files, MinIO objects,
counts/checks и SHA-256 manifest. Существующий каталог не перезаписывается.

## Restore verification

```bash
PHASE8_BACKUP_DIR=./artifacts/phase8-backup \
PHASE8_NAMESPACE=phase8-restore-YYYYMMDD \
make restore-verify
```

Namespace обязан начинаться с `phase8-`. Restore создаёт отдельные PostgreSQL
database, ClickHouse database и MinIO bucket prefix; primary stores не являются
целями. Materialized views создаются после target tables, чтобы не удвоить
aggregates.

Backup пригоден только после проверки manifest, PostgreSQL tables, ClickHouse
facts/aggregate sums/migrations/staging и MinIO objects. Phase 8 восстановил 21
PostgreSQL table, 767,130 referral, 765,182 waiting, 1,508,732 refusal, 2,196
treated rows, шесть записей ClickHouse schema history и восемь MinIO buckets.

При сбое не переключайте приложение на частичный restore. Устраните причину и
повторите в новом `phase8-*` namespace. RPO/RTO владельцем инфраструктуры не
заданы и не заявляются как SLA.

## Изолированный повторяемый drill (2026-09-25)

В отдельном Compose project `phase8-p3-drill-20260925` с новыми volumes
применены Alembic `0001–0008`, ClickHouse migrations `001–006` и создано
восемь MinIO buckets. Для проверки добавлены только синтетические записи:
один регион в PostgreSQL, один treated-snapshot в ClickHouse и один объект в
MinIO. Команда `scripts.operations.backup` создала 31 artifact; команда
`scripts.operations.restore_verify` восстановила их в отдельные БД и buckets
с префиксом `phase8-p3-restore-20260925` и вернула
`RESTORE_CONTENT_VERIFIED`. Проверено: 25 PostgreSQL tables с совпадающими
счётчиками, ограничениями и ревизией; один treated-snapshot, семь записей
истории ClickHouse migrations с совпадающими checksums; восемь MinIO buckets
и SHA-256 восстановленных объектов. Локальное evidence находится в ignored
`artifacts/phase8-p3-drill-20260925-restore.json`; медицинских данных в нём
нет. Действующие `medsignal` volumes не изменялись.

Этот drill проверяет переносимость и восстановление **синтетических** данных,
но не является проверкой application workflow или cross-store snapshot.
PostgreSQL и ClickHouse здесь сверяются по counts/constraints/migration
history и ограниченным агрегатам, не по криптографическому отпечатку каждой
строки; MinIO сверяется по SHA-256 каждого объекта. Перед production RPO/RTO
acceptance потребуется согласовать согласованный момент остановки writers,
целевые RPO/RTO и более сильную сквозную проверку содержимого таблиц.

Для повторения используйте `.env.example` только в отдельном локальном
`phase8-*` project, затем `migrate`, `clickhouse-migrate` и `minio-init`.
После записи синтетических контрольных объектов выполните:

```bash
COMPOSE_ENV_FILES=.env.example python -m scripts.operations.backup \
  --output artifacts/phase8-p3-drill-YYYYMMDD-backup \
  --project phase8-p3-drill-YYYYMMDD
COMPOSE_ENV_FILES=.env.example python -m scripts.operations.restore_verify \
  --backup artifacts/phase8-p3-drill-YYYYMMDD-backup \
  --namespace phase8-p3-restore-YYYYMMDD \
  --project phase8-p3-drill-YYYYMMDD \
  --evidence artifacts/phase8-p3-drill-YYYYMMDD-restore.json
```

Это Bash-синтаксис; в PowerShell задайте `$env:COMPOSE_ENV_FILES` отдельно.
Старые backup artifacts без `verification_version=2` намеренно дают
`RESTORE_VERIFICATION_INCOMPLETE` и не принимаются как доказательство.
