-- MedSignal — отказы в плановой госпитализации (приёмный покой).
--
-- Зерно: один случай отказа.
--
-- Персонального идентификатора в источнике нет, и создавать его здесь
-- незачем: для доли отказов по организации нужен счёт событий, а не
-- различение людей.
--
-- Социальные признаки — статус проживания, страхования и льготная
-- категория — квазиидентификаторы. Они сохранены, потому что доступность
-- помощи анализируется именно в этих разрезах, но выдаются наружу только
-- через агрегаты: доступ к событиям на уровне записи закрыт правами.
--
-- Организация обращения и организация прикрепления различаются по смыслу
-- и хранятся раздельно. Сведение их в одно поле сделало бы невозможным
-- вопрос «куда обратился пациент, прикреплённый к другой организации».

CREATE TABLE IF NOT EXISTS fact_refusal_events
(
    refuse_dt                   DateTime64(3),

    region_source               LowCardinality(String) COMMENT 'Регион обращения как в источнике',
    region_id                   Nullable(UUID),
    hospital_source             LowCardinality(String) COMMENT 'Организация обращения как в источнике',
    hospital_id                 Nullable(UUID),

    attachment_region_source    LowCardinality(String),
    attachment_region_id        Nullable(UUID),
    attachment_hospital_source  LowCardinality(String),
    attachment_hospital_id      Nullable(UUID),

    resident                    LowCardinality(String),
    insured                     LowCardinality(String),
    benefit_category            LowCardinality(String),

    icd10_code                  LowCardinality(String),
    finance_source              LowCardinality(String),
    amount                      Nullable(Decimal(18, 2)) COMMENT 'Предъявленная сумма; пусто примерно в четверти строк',

    import_id                   UUID,
    source_system               LowCardinality(String),
    source_file_hash            String,
    ingested_at                 DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(refuse_dt)
ORDER BY (hospital_source, refuse_dt)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS stg_fact_refusal_events AS fact_refusal_events
ENGINE = MergeTree
PARTITION BY import_id
ORDER BY (import_id, refuse_dt);
