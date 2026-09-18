# GovTech Demo Runbook

Основная демонстрация использует реальные агрегаты Q1 2025. Периодичность
поставки неизвестна, поэтому freshness `UNKNOWN`, а Signal Engine честно
показывает `DATA_STALE`. Development realm и credentials — только для demo.

## Сценарий

1. Войти synthetic `HEALTH_AUTHORITY`.
2. Открыть `/dashboard`: Q1 2025 KPI и mapping limitations.
3. Показать freshness `UNKNOWN` и объяснение.
4. Разделить model validity и temporal freshness forecast.
5. Открыть GLOBAL `DATA_STALE` Signal и evidence.
6. Acknowledge Signal.
7. Preview/save historical `REFERRAL_INFLOW_CHANGE` Scenario.
8. Явно создать Incident, назначить, закрыть с причиной.
9. Показать Audit events.

Scenario называется «Расчётный сценарий». Это не прогноз перегрузки, дефицита
коек или рекомендация AI.

Автоматическая проверка:

```bash
PHASE8_TEST_USERNAME=<synthetic-user> \
PHASE8_TEST_PASSWORD=<local-only-password> \
python scripts/phase8_e2e.py --base-url http://localhost \
  --output artifacts/phase8-e2e.json
```

Safe reset сначала выполняется без `--execute`, затем только для отдельного
`phase8-*` project:

```bash
python -m scripts.demo.reset --project phase8-demo
python -m scripts.demo.reset --project phase8-demo --execute
```

Команда не применяется к основному project, source datasets или реальным
imported facts.
