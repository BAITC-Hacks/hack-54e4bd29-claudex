# Проверка производительности аналитики

`scripts/performance/benchmark.py` измеряет четыре фиксированных агрегирующих
маршрута: overview, referrals/refusals timeseries и organizations. Сценарий
не обращается к строкам пациентов. Токен берётся из
`PERFORMANCE_BEARER_TOKEN`; для локального demo разрешён существующий
`PHASE8_TEST_USERNAME`/`PHASE8_TEST_PASSWORD`. Токен никогда не попадает в
artifact. Укажите фактический размер набора и состояние кэша:

```powershell
$env:PERFORMANCE_BEARER_TOKEN = '<полученный OIDC access token>'
python -m scripts.performance.benchmark `
  --base-url http://localhost `
  --requests 200 --concurrency 20 --cache-state warm `
  --dataset-size '{"referrals":767130,"waiting":765182,"refusals":1508732,"treated":2196}' `
  --output artifacts/performance/analytics-warm.json
```

Для backend-only измерения используйте доступ только из private network и
`--path-mode backend`; получение токена при необходимости направьте через
`--token-base-url`. Нельзя публиковать backend-порт ради benchmark. Значения
20 users и размеры выше — начальная проверка на ранее импортированных
данных, не SLA. Повторяйте cold/warm раздельно и сохраняйте конфигурацию
образов, даты и размер набора рядом с JSON artifact.

В отчёте отдельно указаны число запросов, успешных latency samples,
status counts, p50/p95/p99, error rate, concurrency, cache state и размер
набора. **429, 503, 5xx, network errors и client timeouts не входят в
распределение успешной latency**; они учитываются как ошибки. Edge 429 и
backend 503 нельзя трактовать как быстрые успешные ответы. Необязательные
`--max-error-rate` и `--max-p95-ms` задают проверяемый порог для стабильного
синтетического стенда; без них измерение остаётся описательным.

Nginx access log содержит `$status`, `$upstream_status`,
`$upstream_response_time`, `$request_time`, `request_id` и путь без query
string. В нём нет Authorization, cookies или тела. Это позволяет отдельно
считать edge 429 и upstream 5xx через коллектор логов. Backend Prometheus
считает HTTP status по шаблону route (в том числе backend 429/5xx), latency
аналитических операций и ClickHouse-вызовов, hit/miss/error кэша, а также
длительность фоновых ML-задач. `/metrics` остаётся внутри частной сети.

Текущий локальный контейнерный стенд может отставать от миграций и code HEAD.
Перед сравнением версий проверьте `alembic current`, ClickHouse migrations,
опубликованные импорты и версию приложения. Цифры со старого стенда нельзя
выдавать за benchmark текущей ветки.
