# GovTech Demo Runbook

Основная демонстрация может использовать **только разрешённые** исторические
агрегаты Q1 2025. Периодичность поставки неизвестна, поэтому freshness
`UNKNOWN`, а `DATA_STALE` не является оценкой нагрузки стационара. Не называйте
очередь текущей. Development realm и credentials — только для локального demo.

Для воспроизводимого технического показа без медицинских выгрузок используйте
отдельный `phase8-*` Compose project. Из корня checkout:

```bash
python -m scripts.operations.prepare_acceptance prepare --project phase8-demo-local01
python -m scripts.operations.prepare_acceptance start --project phase8-demo-local01
python -m scripts.acceptance.bootstrap_synthetic --project phase8-demo-local01
python -m scripts.acceptance.verify_scope --project-dir tmp/acceptance/phase8-demo-local01
```

Для browser acceptance установите зависимости frontend (`npm ci`,
`npx playwright install chromium`), задайте `MEDSIGNAL_E2E_BASE_URL` равным
`origin` из игнорируемого manifest и `MEDSIGNAL_E2E_REALM` путём к игнорируемому
`realm.json`, затем выполните `npm run test:e2e` из `frontend/`.
`python -m scripts.acceptance.run_degraded_browser --project phase8-demo-local01`
проверяет настоящий 503 и восстанавливает ClickHouse. Не публикуйте `.env`,
`realm.json`, токены или browser storage state. Остановить проект можно только
явно указав его `--project-name` и собственный overlay; чужие volumes не
затрагивать.

## Сценарий

1. Войти через тестовый Keycloak под synthetic `HEALTH_AUTHORITY` или `ADMIN`.
2. Открыть `/dashboard`: исторический период, source/snapshot и ограничения mapping.
3. Показать freshness `UNKNOWN` и объяснение.
4. Разделить model validity и temporal freshness forecast.
5. Открыть GLOBAL `DATA_STALE` Signal и evidence.
6. Acknowledge Signal.
7. Preview/save historical `REFERRAL_INFLOW_CHANGE` Scenario.
8. Явно создать Incident, назначить, закрыть с причиной.
9. Показать Audit events.

Scenario называется «Расчётный сценарий». Это не прогноз перегрузки, дефицита
коек, освобождения конкретной койки или рекомендация AI. Никаких индивидуальных
дат выписки и медицинских рекомендаций эта демонстрация не обещает.

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
