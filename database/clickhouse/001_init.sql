-- Инициализация аналитической базы (PHASE 1).
--
-- Создаётся только база. Таблицы временных рядов появляются в PHASE 3,
-- после Data Audit: их схема зависит от фактической структуры выгрузок
-- (ADR-0007), и придумывать её заранее нельзя.

CREATE DATABASE IF NOT EXISTS medsignal_analytics;

-- Служебная таблица версий схемы. ClickHouse не имеет собственного
-- механизма миграций, поэтому порядок применения файлов отслеживается явно.
CREATE TABLE IF NOT EXISTS medsignal_analytics.schema_migrations
(
    version     String,
    applied_at  DateTime DEFAULT now()
)
ENGINE = MergeTree()
ORDER BY version;

INSERT INTO medsignal_analytics.schema_migrations (version) VALUES ('001_init');
