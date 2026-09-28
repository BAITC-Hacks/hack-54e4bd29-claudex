# Demo readiness blockers

Проверяемый base SHA: `78ff9fffc0eaee2c01d4568e5b8b9adf84712ab4`. Среда: `phase8-demo-readiness-qa01`, synthetic-only manifest, publication не выполнен.

## P0 — clean acceptance project не достигает READY

- Владелец: acceptance / infrastructure orchestration.
- Шаги воспроизведения:
  1. Создать отдельный project командой `prepare` на SHA `78ff9ff...`.
  2. Убедиться, что project-prefixed volumes новые, source dir пуст, host port свободен.
  3. Выполнить штатный `start` один раз.
- Ожидание: migration one-shot services завершаются успешно, nginx начинает слушать loopback origin, launcher записывает `READY`.
- Фактически: `clickhouse-migrate` завершился exit 1; его безопасная причина — `Connection refused` к `clickhouse:8123` до готовности сервиса. Один повтор штатного `start` остановился на `preflight_images / IMAGE_INSPECT_FAILED` для всех шести project-built images.
- Evidence: ignored `tmp/acceptance/phase8-demo-readiness-qa01/sanitized-diagnostics.json`; container log `clickhouse-migrate` без credentials и данных.
- Предполагаемые файлы владельца: `scripts/operations/prepare_acceptance.py`, dependency/readiness declaration `clickhouse-migrate` в Compose.
- Критерий закрытия: первый `start` на новом project и новых volumes стабильно выполняет migration после доступности ClickHouse, сохраняет inspectable image IDs и проходит launcher verification без ручного retry.

## P1 — synthetic demo маркируется как real/official

- Владелец: design + frontend copy.
- Шаги воспроизведения: статически открыть `frontend/src/app/command-center/page.tsx` и `frontend/src/components/site-header.tsx`; после восстановления runtime проверить те же строки в браузере.
- Ожидание: synthetic acceptance не представлен как реальные данные или официальный интерфейс ведомства.
- Фактически и предлагаемый текст:
  - `Минздрав РК` → `Демонстрационный контур`.
  - `Загружаем реальные агрегаты…` → `Загружаем агрегаты…`.
  - `Карта фактической нагрузки` → `Карта исторических показателей`.
  - `Реальные строки источников` → `Строки тестовых источников` в synthetic demo либо нейтральное `Строки источников`.
- Evidence: точные строки в указанных файлах; browser rendering NOT TESTED из-за P0.
- Критерий закрытия: synthetic mode явно обозначен на экране; нет слов, создающих впечатление live/official data или доказанной нагрузки; browser test на integrated SHA подтверждает текст.

## P2 — основная навигация рендерится до входа

- Владелец: frontend/auth UX.
- Шаги воспроизведения: открыть защищённый route без OIDC token; статически `SiteHeader` всегда рендерит `Основная навигация` независимо от `isAuthenticated`.
- Ожидание: рабочая навигация скрыта до входа согласно принятому demo-дизайну; серверная авторизация остаётся отдельной обязательной проверкой.
- Фактически: links `Карта`, `Мониторинг`, `Аналитика`, `Сигналы`, `Сценарии`, `Организации`, `Регионы` создаются до ветвления кнопки входа.
- Evidence: `frontend/src/components/site-header.tsx`; новый тест `auth-and-scope.spec.ts` фиксирует ожидаемое поведение, но runtime assertion NOT TESTED.
- Критерий закрытия: navigation отсутствует до входа, прямой API/URL по-прежнему проверяется backend и возвращает unauthenticated/not-found согласно scope.

## Координационная граница

Готовность forecast и проверка MAE имеют статус `BLOCKED_BY_FORECAST_WORK`. Это не P0 acceptance и не подтверждение качества прогноза. После передачи артефакта первым агентом нужны даты, единицы и метрика с API/экрана на новом объединённом SHA; MAE нельзя называть процентом точности.
