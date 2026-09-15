# Архитектура описательной аналитики

## Назначение

PHASE 4 даёт пользователю агрегированное представление загруженных данных. Этот слой не прогнозирует нагрузку, не рассчитывает коечную занятость и не формирует рекомендации.

```mermaid
flowchart LR
    UI[Next.js Situation Center] -->|Bearer token + filters| API[FastAPI /api/v1/analytics]
    API --> Service[AnalyticsService]
    Service --> Policy[Permission + SecurityContext]
    Service --> PG[(PostgreSQL metadata)]
    Service --> Cache[(Redis cache)]
    Service --> Repo[AnalyticsRepository]
    Repo --> CH[(ClickHouse facts)]
```

API выполняет аутентификацию, проверяет форму запроса и сериализует ответ. `AnalyticsService` применяет permission и data scope, формирует metadata/limitations и изолированный cache key. Репозиторий выполняет только агрегирующие параметризованные запросы. Frontend не получает строки событий.

## Идентичность организаций

Каноническая организация имеет ссылку `canonical:<uuid>`. Несопоставленное значение имеет непрозрачную ссылку `source:<sha256>`, рассчитанную из пространства источника и нормализованного значения. Пространства `REFERRALS:RECEIVING`, `WAITING:DESTINATION`, `REFUSALS:INCOMING` и `TREATED:ORGANIZATION` не объединяются автоматически.

Несопоставленные организации доступны только `ADMIN` и `HEALTH_AUTHORITY`. Региональные и госпитальные роли видят только факты с подтверждённым `hospital_id` в своей области.

## Ограничения запросов

- период ограничен `ANALYTICS_MAX_DATE_RANGE_DAYS`, по умолчанию 366;
- временной ряд возвращает максимум 400 агрегированных точек;
- список организаций постраничный, максимум 100 строк;
- granularity ограничена `DAY` и `WEEK`;
- profile, region и organization передаются как параметры; SQL-поля выбираются из закрытых allowlist;
- ошибки ClickHouse наружу не возвращаются.

## Наблюдаемость

Prometheus получает число и latency агрегатных операций, а также cache hit/miss/error. Метки содержат только низкокардинальные имена операций и исходы.
