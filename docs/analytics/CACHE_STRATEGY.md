# Стратегия кэша аналитики

Redis ускоряет дорогие `overview` и постраничный `organizations` и не является источником истины. При недоступности Redis запрос выполняется в ClickHouse; состояние импорта остаётся в PostgreSQL.

Ключ строится из:

- имени endpoint;
- периода, granularity, profile, region и organization filters;
- разрешённого SecurityContext scope;
- разрешения на unmapped records;
- идентификаторов опубликованных файлов поставок и исторических legacy imports;
- verified mapping version и decision generation.
- номера страницы и размера страницы для `organizations`.

TTL задаёт `ANALYTICS_CACHE_TTL_SECONDS` (60 секунд по умолчанию). Новая опубликованная поставка меняет watermark и автоматически переводит запрос на новый ключ. Ключи разных областей данных не совпадают.

Кэш списка содержит только ограниченную страницу агрегатов (не событийные строки). Названия канонических организаций повторно берутся одним batch-запросом из PostgreSQL: изменение имени не остаётся в кэше ClickHouse. Перед выдачей даже кэшированного результата повторно проверяется PG publication snapshot. Неподтверждённый mapping для ограниченного scope закрывает доступ до чтения кэша.

Метрики `medsignal_analytics_cache_access_total{endpoint,result}` различают `hit`, `miss` и `error`. Содержимое ключа хешируется SHA-256 и не содержит token/user identity или source organization value.


D3 binds one immutable PG publication snapshot across each response. Every fact query uses the same import allowlist and exact mapping version, including totals, timeseries, organization detail, waiting and coverage. Unpublished delivery parts are excluded even if their file import completed. Legacy imports remain historical only.

A role alone never grants global/unmapped access: effective resolved `scope.is_global` is required. Restricted queries require a verified active mapping before a cache read. Before returning any query/cache result, PG metadata is reread; a changed publication/mapping generation rejects the response. Old Redis entries can expire naturally because their keys cannot authorize a revoked scope. Redis errors retain the existing query fallback; PG/CH uncertainty never broadens scope.

Global quality counts are omitted for restricted users with `GLOBAL_QUALITY_TOTALS_RESTRICTED`. Partial file counts appear only in global quality and explicitly carry PARTIAL/INCOMPLETE_DELIVERY. Mapping unavailability and incomplete delivery are visible UI states.
