# Scenario Analysis

## Назначение

Phase 7 отвечает только на вопрос: «Как выглядело бы выбранное число направлений при явно заданном гипотетическом изменении входящего потока?» Это детерминированный расчётный сценарий, а не Forecast, рекомендация, оценка перегрузки или расчёт коек.

Поддерживается один тип `REFERRAL_INFLOW_CHANGE` и четыре допущения: −20%, −10%, +10%, +20%.

## Baseline

`OBSERVED` сервер получает через существующий агрегированный analytics path за включительный период и scope. Клиент не передаёт authoritative `baseline_value`.

`FORECAST` сервер получает по `forecast_id` из PostgreSQL. Forecast должен иметь target `DAILY_REFERRAL_COUNT`, structural status `VALID`, период и dataset watermark. Temporal freshness вычисляется независимо. `STALE` Forecast разрешён только с `historical_analysis=true` и всегда маркируется историческим.

## Расчёт

```text
calculated_value = baseline_value × (1 + assumption_value)
delta_absolute = calculated_value − baseline_value
delta_percent = assumption_value
```

Все значения рассчитываются `Decimal`, округление `ROUND_HALF_UP`, precision 4 decimal places. Версия формулы: `referral_inflow_change.v1`.

## Preview и Save

Preview читает baseline и возвращает расчёт без PostgreSQL record и AuditEvent. Save не доверяет preview: заново читает baseline и пересчитывает authoritative result. Scenario и `SCENARIO_CREATED` коммитятся одной Unit of Work.

Сохранённая Scenario immutable. Retry защищён `(created_by, client_request_id)`. Тот же ключ и тот же запрос возвращают существующую запись; другой запрос с тем же ключом даёт `409 CONFLICT`.

## Scope и связи

GLOBAL/REGION/HOSPITAL повторяют правила Phase 6. GLOBAL доступен только global scope. Source Signal/Incident необязательны, обязаны быть видимыми и иметь точно тот же scope. Scenario не создаёт Incident и не меняет Signal/Incident.

## Ограничения

> Расчётный сценарий. Не является прогнозом или рекомендацией. Решение принимает уполномоченный сотрудник.

Расчёт меняет только число направлений. Он не моделирует койки, госпитализации, выписки, длительность лечения, персонал, занятость или дефицит мощности. Изменение referrals нельзя интерпретировать как hospital overload.

## API и UI

- `POST /api/v1/scenarios/preview`
- `POST /api/v1/scenarios`
- `GET /api/v1/scenarios`
- `GET /api/v1/scenarios/{id}`
- UI: `/scenarios`

Entry points: Situation Center и Signal detail. Incident frontend entry point в Phase 7 отсутствует.

## Проверка

```bash
pytest backend/tests/unit/test_scenario_calculation.py backend/tests/unit/test_scenario_service.py
pytest backend/tests/integration/test_scenario_api.py
cd frontend && npm run test && npm run lint && npm run typecheck && npm run build
```

