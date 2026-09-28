-- MedSignal — суточные агрегаты.
--
-- Создаются два агрегата и ровно два. Каждый отвечает на вопрос, который
-- интерфейс задаёт постоянно: сколько направлений и сколько отказов
-- пришлось на организацию за день. Умозрительные разрезы «на будущее»
-- здесь не заводятся: неиспользуемое представление всё равно
-- пересчитывается при каждой вставке и молча расходится со смыслом,
-- когда меняется таблица фактов.
--
-- Представления наполняются при вставке в таблицу фактов. Поэтому загрузка
-- обязана идти через публикацию из промежуточной таблицы в фактовую:
-- вставка мимо неё оставит агрегаты пустыми.
--
-- Агрегат построен на исходном идентификаторе организации, а не на
-- сопоставленном. Сопоставление появится позже и изменится задним числом;
-- агрегат, зависящий от него, пришлось бы пересчитывать целиком.

CREATE TABLE IF NOT EXISTS agg_referrals_daily
(
    event_date         Date,
    receiving_org_key  LowCardinality(String),
    referrals          UInt64
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(event_date)
ORDER BY (receiving_org_key, event_date);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_referrals_daily
TO agg_referrals_daily
AS
SELECT
    toDate(registration_dt) AS event_date,
    receiving_org_key,
    count() AS referrals
FROM fact_referral_events
GROUP BY event_date, receiving_org_key;

CREATE TABLE IF NOT EXISTS agg_refusals_daily
(
    event_date       Date,
    hospital_source  LowCardinality(String),
    refusals         UInt64
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(event_date)
ORDER BY (hospital_source, event_date);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_refusals_daily
TO agg_refusals_daily
AS
SELECT
    toDate(refuse_dt) AS event_date,
    hospital_source,
    count() AS refusals
FROM fact_refusal_events
GROUP BY event_date, hospital_source;
