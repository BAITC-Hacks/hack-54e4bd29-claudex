# Demo readiness backup plan

## Зафиксированная база

- Код: `78ff9fffc0eaee2c01d4568e5b8b9adf84712ab4`.
- QA branch: `feature/demo-readiness-qa`.
- Проверенный prepare manifest: `phase8-demo-readiness-qa01`, `synthetic-only`, origin `127.0.0.1:64243`, status `PREPARED`.
- Этот project не является готовым запасным live-стендом: `start` не достиг `READY`.
- Synthetic publication version `phase8-synthetic-fixture-v1` в этой среде не опубликована.
- После сбора diagnostics partial containers/network и disposable volumes `qa01` удалены; ignored manifest, realm и sanitized diagnostics сохранены локально. Для следующего прогона требуется новый project name и новые volumes.

## Локальные ресурсы

- Docker images, собранные штатным acceptance launcher на exact SHA.
- Новый уникальный `phase8-demo-readiness-*` namespace с собственными volumes, loopback port, private ignored `.env` и realm.
- Зафиксированные frontend dependencies (`npm ci`) и установленный Chromium/Chrome для Playwright.
- Никаких API keys, realm contents, cookies, tokens или storage state в репозитории и evidence.

## Проверка перед выступлением

1. Создать новый project с уникальным именем; не переиспользовать `qa01`, где migration уже запускался.
2. Выполнить штатные `prepare`, `start`, `bootstrap_synthetic` и `verify_scope`. Не обходить failure/security gate.
3. Проверить manifest: exact SHA, `dataset=synthetic-only`, project-prefixed volumes, loopback origin, пустой внешний source до bootstrap.
4. Выполнить `npx playwright test e2e/demo-readiness`. Требование: 4 выполнено, 4 passed, 0 failed, 0 skipped.
5. Выполнить frontend unit/typecheck/lint/build и записать свежий результат отдельно от browser PASS.
6. Проверить, что выделенный demo signal имеет `NEW`; после репетиции создать новый одноразовый project вместо reset чужой базы.

Если первый clean `start` снова падает, live-показ отменяется: не выполнять ручной Compose workaround и не использовать стенд коллег.

## Если LLM недоступен

- Оставить `COPILOT_ENABLED=false`.
- Показать фактический `COPILOT_DISABLED` и сохранение исходной карточки.
- Не добавлять API key и не выполнять платный smoke.
- Existing fixture-success можно показать только как «UI fixture», не как live ответ модели.

## Если интернет недоступен

- Keycloak/API остаются локальными, если images и dependencies подготовлены заранее.
- Внешние OpenStreetMap tiles могут не загрузиться; перейти на `Аналитика` и таблицу организаций, не утверждать, что карта полностью доступна.
- Не заменять недоступный forecast или Copilot выдуманными значениями.

## Если runtime недоступен

- Показать документы/API contract и код тестов как материалы, а не live demo.
- На текущем SHA проверенной записи полного маршрута нет; поэтому нельзя называть старый скриншот или fixture live-демонстрацией.
- Сообщить статус `BLOCKED`, P0 и SHA. Продолжить только после нового clean-environment PASS.

## После интеграции

Forecast и design changes требуют нового short pass на объединённом SHA. PASS от `78ff9ff...` (которого browser run не получил) не переносится автоматически.
