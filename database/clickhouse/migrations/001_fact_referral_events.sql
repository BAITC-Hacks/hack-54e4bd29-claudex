-- MedSignal — направления на плановую госпитализацию.
--
-- Зерно: одно направление из исходной выгрузки ИС БГ.
--
-- Ни одного персонального идентификатора здесь нет. Исходный
-- hospitalization_code содержит порядковый номер пациента и в аналитическое
-- хранилище не попадает ни в каком виде: вместо него хранится event_key —
-- псевдоним, полученный HMAC-SHA256 с ключом из окружения.
--
-- diagnosis_name намеренно отсутствует. Для аналитики достаточно кода
-- МКБ-10; читаемое наименование — это данные о здоровье на уровне записи,
-- и его место в ограниченном справочнике, а не в таблице фактов.
--
-- Организация хранится дважды: receiving_org_key — нормализованное значение
-- из источника, оно есть всегда; receiving_hospital_id — сопоставленная
-- организация справочника, её может не быть. Порядок сортировки построен
-- на первом: сортировать по столбцу, который в трети строк пуст, нельзя.

CREATE TABLE IF NOT EXISTS fact_referral_events
(
    event_key             String COMMENT 'HMAC-псевдоним кода случая; исходный код не хранится',

    registration_dt       DateTime64(3) COMMENT 'Дата регистрации направления',
    planned_dt            Nullable(DateTime64(3)) COMMENT 'Плановая дата госпитализации',
    polyclinic_dt         Nullable(DateTime64(3)),
    hospitalization_dt    Nullable(DateTime64(3)) COMMENT 'Факт госпитализации; известен после точки прогноза',
    refusal_dt            Nullable(DateTime64(3)) COMMENT 'Отказ; пусто для несостоявшихся отказов, это норма',

    referring_org_key     LowCardinality(String) COMMENT 'Нормализованное наименование направляющей организации',
    receiving_org_key     LowCardinality(String) COMMENT 'Нормализованное наименование принимающей организации',
    referring_hospital_id Nullable(UUID) COMMENT 'Организация справочника; пусто, пока сопоставление не подтверждено',
    receiving_hospital_id Nullable(UUID),

    profile_source        LowCardinality(String) COMMENT 'Профиль койки как в источнике; пустая строка = отсутствует',
    canonical_profile_id  Nullable(UUID),

    icd10_code            LowCardinality(String),
    territorial_type      LowCardinality(String),
    referral_purpose      LowCardinality(String),
    finance_source        LowCardinality(String),

    import_id             UUID COMMENT 'Связь с DataImport в PostgreSQL',
    source_system         LowCardinality(String),
    source_file_hash      String COMMENT 'SHA-256 исходного файла: происхождение строки восстановимо',
    ingested_at           DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(registration_dt)
ORDER BY (receiving_org_key, registration_dt, event_key)
SETTINGS index_granularity = 8192;

-- Промежуточная таблица загрузки. Разбиение по import_id даёт мгновенное
-- и точное удаление данных незавершённого импорта: ClickHouse и PostgreSQL
-- не образуют одной транзакции, поэтому граница «опубликовано» проводится
-- явно, а не подразумевается.
CREATE TABLE IF NOT EXISTS stg_fact_referral_events AS fact_referral_events
ENGINE = MergeTree
PARTITION BY import_id
ORDER BY (import_id, registration_dt);
