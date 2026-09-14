-- MedSignal — ожидающие плановую госпитализацию.
--
-- Зерно: одна запись очереди из одной поставленной выгрузки.
--
-- ВАЖНО о семантике времени. Data Audit показал, что выгрузка содержит одну
-- отметку загрузки на весь файл. Это значит, что перед нами один срез,
-- а не история срезов. Столбец snapshot_dt хранит дату этого среза, и
-- запрос «как менялась очередь» на текущих данных ответа не имеет: срез
-- пока единственный. Поле существует ради будущих поставок, а не ради
-- иллюзии истории.
--
-- patient_seq_no — порядковый номер пациента внутри кода госпитализации.
-- В хранилище он не попадает. patient_key — HMAC-псевдоним составного
-- значения (регион, организация, профиль, номер): номер сам по себе
-- не уникален и без остальных частей псевдоним склеил бы разных людей.
--
-- Сведения об операции сведены к признаку наличия. Код и наименование
-- вмешательства — данные о здоровье на уровне записи, и для расчёта
-- размера очереди они не нужны.

CREATE TABLE IF NOT EXISTS fact_waiting_events
(
    patient_key            String COMMENT 'HMAC-псевдоним составного идентификатора записи очереди',

    registration_dt        DateTime64(3) COMMENT 'Дата постановки в очередь',
    planned_dt             Nullable(DateTime64(3)),
    snapshot_dt            DateTime64(3) COMMENT 'Дата среза очереди, а не отчётный период',

    region_source          LowCardinality(String) COMMENT 'Код региона как в источнике',
    region_id              Nullable(UUID),

    hospital_source        LowCardinality(String) COMMENT 'Код организации назначения как в источнике',
    hospital_id            Nullable(UUID),

    profile_source         LowCardinality(String),
    profile_id             Nullable(UUID),

    icd10_code             LowCardinality(String),
    has_operation          UInt8 COMMENT 'Признак наличия сведений об операции; сама операция не хранится',

    import_id              UUID,
    source_system          LowCardinality(String),
    source_file_hash       String,
    ingested_at            DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(registration_dt)
ORDER BY (hospital_source, registration_dt, patient_key)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS stg_fact_waiting_events AS fact_waiting_events
ENGINE = MergeTree
PARTITION BY import_id
ORDER BY (import_id, registration_dt);
