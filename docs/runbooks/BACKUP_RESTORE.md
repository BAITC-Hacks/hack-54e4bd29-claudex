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
