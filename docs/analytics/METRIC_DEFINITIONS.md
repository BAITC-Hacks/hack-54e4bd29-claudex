# Определения метрик

Единый программный реестр находится в `backend/app/business/analytics/metrics.py`. Формула не дублируется в контроллерах и React-компонентах.

| Метрика | Смысл | Источник и формула | Зерно | Ограничения |
|---|---|---|---|---|
| `REFERRALS_TOTAL` | Зарегистрированные направления | `count()` из `fact_referral_events` по `registration_dt` | организация источника × период | Считает события, не пациентов |
| `WAITING_RECORDS` | Записи в подтверждённом срезе ожидания | `count()` одного последнего подтверждённого и опубликованного `snapshot_dt` при одинаковых filters/scope во всех ответах | снимок × организация источника | `null`, если нет подтверждённой поставки; не историческая очередь |
| `REFUSALS_TOTAL` | События отказа | `count()` из `fact_refusal_events` по `refuse_dt` | организация источника × период | Отношение к направлениям не рассчитывается |
| `OBSERVED_WAITING_MEAN_DAYS` | Среднее время до завершённой госпитализации | `avg(hospitalization_dt-registration_dt)` | период × организация | Чувствительно к выбросам; конфликты исключены |
| `OBSERVED_WAITING_MEDIAN_DAYS` | Медианное наблюдаемое ожидание | TDigest P50 корректных завершённых записей | период × организация | Не прогноз |
| `OBSERVED_WAITING_P75_DAYS` | P75 наблюдаемого ожидания | TDigest P75 | период × организация | Не включает открытые направления |
| `OBSERVED_WAITING_P90_DAYS` | P90 наблюдаемого ожидания | TDigest P90 | период × организация | Не включает открытые направления |
| `QUEUE_AGE_MEDIAN_DAYS` | Медианный возраст текущей очереди | P50 от `snapshot_dt-registration_dt` | снимок × организация | Снимок, не trend |
| `QUEUE_AGE_P75_DAYS` | P75 возраста текущей очереди | TDigest P75 | снимок × организация | Снимок |
| `QUEUE_AGE_P90_DAYS` | P90 возраста текущей очереди | TDigest P90 | снимок × организация | Снимок |
| `QUEUE_AGE_OLDEST_DAYS` | Максимальный возраст записи | `max(snapshot_dt-registration_dt)` | снимок × организация | Требует корректной хронологии |

`hospitalized_total` в overview означает направление с заполненной `hospitalization_dt`, не имеющее приоритетного отказа и не нарушающее хронологию. `data_quality_warnings` в overview — число направлений с датой госпитализации или отказа раньше регистрации.

Процент отказов не реализован: соответствие числителя и знаменателя между двумя выгрузками не доказано. Показатели загрузки/занятости не реализованы: отсутствует знаменатель коечной мощности.


## D3 publication, completeness and dates (2026-09-23)

All descriptive counts resolve exact approved organization/region projections before applying scope and aggregation. Matching text in another identity_space is not a match. Global governance preserves unmatched facts; restricted hospital/region users see only resolved canonical scope. New facts must belong to a PUBLISHED delivery. Legacy imports remain historical without a claim of confirmed completeness. Raw rows are not exposed by these contracts.

Daily sums and overview counts must use identical period bounds, mapping version, import IDs and effective scope. `ImportWatermark` is a historical descriptive allowlist; operational adapters instead consume `DeliveryReadiness.published_import_ids` and its confirmed complete-through date.

Freshness separates event period, source load date, last successful file import, owner-confirmed complete-through date, cadence and completeness. A new load of Q1 2025 facts cannot make their event coverage CURRENT. Unknown cadence/date is UNKNOWN; incomplete reservations/parts are PARTIAL. Cadence-based CURRENT only describes reviewed delivery recency; `forecast_available=false` in descriptive freshness does not approve any model. Model eligibility is a separate R/M gate.

Queue age is null with SNAPSHOT_SEMANTICS_UNCONFIRMED until owner-confirmed snapshot semantics and observed snapshot evidence agree. Once confirmed, summary, overview and organization aggregates use the same latest eligible published snapshot for identical filters and scope. An unrelated approval does not validate a legacy snapshot. `snapshot_at` is null if no eligible snapshot exists; neither `source_load_date` nor `import_completed_at` is substituted. TREATED load time remains a source-load timestamp, never an inferred reporting period. Quality exact totals are global-only; partial totals are explicitly labeled.
