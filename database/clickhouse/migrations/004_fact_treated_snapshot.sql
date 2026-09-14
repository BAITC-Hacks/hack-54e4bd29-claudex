-- MedSignal — пролеченные случаи по медицинским организациям.
--
-- Зерно: одна организация в одной поставленной выгрузке.
--
-- ЭТО НЕ ВРЕМЕННОЙ РЯД. Столбец snapshot_load_dt — момент выгрузки данных,
-- а не отчётный период, к которому относятся показатели. Отчётного периода
-- в источнике нет вовсе, и восстановить его неоткуда. Имя столбца выбрано
-- так, чтобы ошибиться было трудно: reporting_period здесь отсутствует
-- намеренно, а не забыт.
--
-- Пока владелец данных не сообщит отчётный период, эта таблица пригодна
-- только для среза «текущее состояние» и непригодна для динамики.

CREATE TABLE IF NOT EXISTS fact_treated_snapshot
(
    hospital_source        LowCardinality(String) COMMENT 'Наименование организации как в источнике',
    hospital_id            Nullable(UUID),

    discharged_total       UInt32,
    discharged_children    UInt32,
    treated_budget         UInt32,
    treated_paid           UInt32,
    discharged_within_day  UInt32,
    deaths_total           UInt32,
    bed_days               UInt64,
    amount_to_pay          Decimal(20, 2),

    snapshot_load_dt       DateTime64(3) COMMENT 'Момент выгрузки. НЕ отчётный период',

    import_id              UUID,
    source_system          LowCardinality(String),
    source_file_hash       String,
    ingested_at            DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(snapshot_load_dt)
ORDER BY (hospital_source, snapshot_load_dt)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS stg_fact_treated_snapshot AS fact_treated_snapshot
ENGINE = MergeTree
PARTITION BY import_id
ORDER BY (import_id, hospital_source);
