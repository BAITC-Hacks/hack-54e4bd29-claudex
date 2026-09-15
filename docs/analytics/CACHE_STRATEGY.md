# Стратегия кэша аналитики

Redis ускоряет только дорогой overview и не является источником истины. При недоступности Redis запрос выполняется в ClickHouse; состояние импорта остаётся в PostgreSQL.

Ключ строится из:

- имени endpoint;
- периода, granularity, profile, region и organization filters;
- разрешённого SecurityContext scope;
- разрешения на unmapped records;
- идентификаторов и времени последних завершённых импортов.

TTL задаёт `ANALYTICS_CACHE_TTL_SECONDS` (60 секунд по умолчанию). Новый завершённый импорт меняет watermark и автоматически переводит запрос на новый ключ. Ключи разных областей данных не совпадают.

Метрики `medsignal_analytics_cache_access_total{endpoint,result}` различают `hit`, `miss` и `error`. Содержимое ключа хешируется SHA-256 и не содержит token/user identity или source organization value.
