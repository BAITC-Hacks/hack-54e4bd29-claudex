# Copilot API v1 — объяснение сигнала (synthetic demo)

`POST /api/v1/copilot/explain-signal` принимает только `{ "signal_id": "<UUID>" }` и Bearer token Keycloak. Существующий `SignalService.get_signal` проверяет право `signal.read` и область данных до обращения к LLM. Недоступный сигнал возвращает тот же `404`, что и отсутствующий.

Ответ `200` содержит отдельный необязательный LLM-слой; исходное алгоритмическое `SignalExplanation` и существующие endpoints не меняются:

```json
{
  "signal_id": "11111111-1111-4111-8111-111111111111",
  "signal_version": 1,
  "title": "Пояснение сигнала: рост очереди",
  "explanation": "Сработало правило роста очереди. Доступные синтетические показатели показывают увеличение относительно периода сравнения. Это описание наблюдаемого изменения, а не установленная причина. По этим данным нельзя сделать вывод о наличии свободных коек или о причинах изменения потока. Проверку и решение выполняет уполномоченный сотрудник.",
  "fact_ids": ["F1"],
  "facts": [{
    "id": "F1", "metric_code": "queue_size", "label": "Размер очереди",
    "value": 21.0, "unit": "percent_change", "direction": "INCREASE",
    "period_start": "2025-01-01T00:00:00Z", "period_end": "2025-01-28T23:59:59Z",
    "source": "signal_explanation"
  }],
  "evaluation_period_start": null,
  "evaluation_period_end": null,
  "reference_period_start": null,
  "reference_period_end": null,
  "data_current": false,
  "data_watermark_at": null,
  "limitations": ["Синтетические демонстрационные данные; выводы о реальной нагрузке недопустимы."],
  "generated_at": "2026-09-26T12:00:00Z",
  "request_id": "example-request-id",
  "llm_generated": true,
  "provider": "openai",
  "model": "gpt-4.1-mini-2025-04-14"
}
```

Числа, единицы, даты, ссылки на факты и происхождение в ответе формирует backend. `fact_ids` из модели проходят проверку по фактам текущего запроса; текст модели не может содержать числовых утверждений. `null` означает неизвестное значение: время импорта не подставляется вместо даты снимка. `data_current=false` не означает текущую очередь. Если дата или показатель неизвестны, соответствующее поле остаётся `null` или факт отсутствует. Отсутствие фактов не заменяется выдуманным пояснением.

Ошибки используют общий envelope `{ "error": { "code": "...", "message": "...", "details": {}, "request_id": "..." } }`:

| Случай | HTTP | code |
| --- | --- | --- |
| Нет/неверный токен | 401 | `UNAUTHENTICATED` |
| Сигнал вне scope или отсутствует | 404 | `NOT_FOUND` |
| Недостаточно разрешённых фактов / происхождение не подтверждено | 422 | `COPILOT_INSUFFICIENT_DATA` |
| Copilot выключен | 503 | `COPILOT_DISABLED` |
| Provider не настроен/недоступен | 503 | `COPILOT_PROVIDER_UNAVAILABLE` |
| Provider timeout | 504 | `COPILOT_PROVIDER_TIMEOUT` |
| Некорректный structured output или непроверенные утверждения | 502 | `COPILOT_INVALID_RESPONSE` |
| Превышен лимит synthetic demo | 429 | `COPILOT_RATE_LIMITED` |

Примеры запросов для error-состояний используют тот же JSON. Ни один error-ответ не выдаёт заранее приготовленный AI-текст. UI должен различать loading, disabled, unavailable, insufficient data и 404; существующая карточка сигнала продолжает показывать алгоритмическое объяснение независимо от Copilot.

Внешняя передача в v1 разрешена только для серверно подтверждённых synthetic demo signals. `COPILOT_ENABLED=false` по умолчанию. Настройки сервера: `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4.1-mini-2025-04-14`, `LLM_TIMEOUT_SECONDS=30`, `LLM_MAX_OUTPUT_TOKENS=1200`; ключ только через `LLM_API_KEY` в среде backend. Responses API вызывается со `store=false`, без tools. Реальные медицинские данные и даже реальные агрегаты не отправляются автоматически. Prompt/response целиком не сохраняются и не логируются. Эта функция не делает медицинских или управленческих рекомендаций.

Для локального теста задайте `LLM_API_KEY` непосредственно в окружении backend-процесса, затем `COPILOT_ENABLED=true`. Base/production Compose в этой ветке не изменён и эти переменные автоматически в контейнер не пробрасывает. Для изолированного synthetic acceptance есть [локальный launcher с закрытым вводом ключа](LIVE_VERIFICATION.md). Не помещайте ключ в обычный `.env`, shell history, логи, frontend или Git; единственное локальное исключение — буквальный `copilot.env` **вне репозитория и Docker build context**, описанный в инструкции launcher. По умолчанию endpoint возвращает `COPILOT_DISABLED`; отсутствие ключа при включённой функции возвращает `COPILOT_PROVIDER_UNAVAILABLE`, не влияет на `/ready` и обычные endpoints. Лимит synthetic demo — 6 запросов на субъект за скользящую минуту и 2 одновременных вызова на процесс; это локальное ограничение, а не распределённый production rate limit.

Синтетические error-примеры (все используют тот же `signal_id`, если не сказано иначе):

```json
{"error":{"code":"COPILOT_INSUFFICIENT_DATA","message":"Недостаточно разрешённых фактов для пояснения","details":{},"request_id":"example-request-id"}}
{"error":{"code":"COPILOT_DISABLED","message":"Copilot отключён","details":{},"request_id":"example-request-id"}}
{"error":{"code":"COPILOT_PROVIDER_TIMEOUT","message":"Превышено время ожидания сервиса пояснений","details":{},"request_id":"example-request-id"}}
{"error":{"code":"COPILOT_PROVIDER_UNAVAILABLE","message":"Сервис пояснений временно недоступен","details":{},"request_id":"example-request-id"}}
{"error":{"code":"NOT_FOUND","message":"Сигнал не найден","details":{},"request_id":"example-request-id"}}
```

Последняя строка одинаково описывает отсутствующий и недоступный по scope сигнал. Пояснение не является медицинской рекомендацией или доказательством первопричины. Числовые и ссылочные проверки ограничивают известные классы ошибок, но не гарантируют отсутствие всех возможных галлюцинаций. Поставщик/формат проверены по [официальной документации Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) и [странице зафиксированного snapshot модели](https://developers.openai.com/api/docs/models/gpt-4.1-mini).
