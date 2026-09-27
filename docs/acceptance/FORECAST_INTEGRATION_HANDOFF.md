# Forecast demo: передача на интеграцию и QA

## Код и границы результата

- Функциональная база: `78ff9fffc0eaee2c01d4568e5b8b9adf84712ab4`
  (`feature/copilot-signal-explanation`), не старый `main`.
- HEAD проверенного кода перед этим документом:
  `e411458b8fb10384b0e5a746e01f8c7d220bc904` в локальной ветке
  `feature/demo-forecast-validation`. Коммит этого документа меняет tip;
  его фактический SHA проверяется `git rev-parse HEAD`.
- Два исходных коммита задачи:
  `9d224384c69d75db02694965f07f0c8d1098e9f4` — synthetic fixture,
  verifier и точечный MLflow host allowlist;
  `ef6f609bb91ddc084233d2c0e8b0eb91a20bc285` — период validation
  в API, подписи карточки и отчёт. Дополнительный минимальный fix
  `e411458b8fb10384b0e5a746e01f8c7d220bc904` допускает явную
  synthetic-подпись при `NEXT_PUBLIC_APP_ENV=test`; production остаётся
  исключённым.
- Push, PR, merge, deployment и платные LLM-вызовы не выполнялись.

Изменённые группы файлов:

| Область | Файлы |
|---|---|
| Synthetic evidence | `scripts/acceptance/forecast_demo_fixture.py`, `scripts/acceptance/verify_forecast_pairs.py`, `tests/operations/test_forecast_demo_fixture.py`, `tests/operations/test_verify_forecast_pairs.py` |
| API | `backend/app/business/forecasting/contracts.py`, `backend/app/business/forecasting/service.py`, `backend/app/schemas/forecasting.py`, `backend/app/api/v1/forecasts.py`, три forecast test files в `backend/tests/` |
| UI | `frontend/src/features/forecasting/components/referral-forecast-card.tsx` и `.test.tsx`, `frontend/src/features/forecasting/types.ts`, `frontend/src/features/forecasting/demo-context.ts` и `.test.ts`, `frontend/src/app/dashboard/page.tsx`, `frontend/Dockerfile`, `.env.example` |
| Opt-in browser QA | `frontend/e2e/forecast-demo.spec.ts`, `frontend/playwright.config.ts` |
| Инфраструктура | `docker-compose.yml`, `tests/operations/test_mlflow_host_allowlist.py` |
| Документация | `docs/acceptance/FORECAST_DEMO_VERIFICATION.md`, этот handoff |

Сохранённый synthetic forecast `f89d1fd5-2f20-4810-9491-4f42aa2e3ed1`
существовал в **старом** изолированном project `phase8-accept-20260926e`.
Новый project может создать иной UUID. Источник — два явно синтетических
пакета: 30 строк 01–02.01.2025 и `source-forecast/manifest-REFERRALS-forecast-demo.json`
с delivery `phase8-synthetic-forecast-referrals-v1`, 1 989 строк
03.01–31.03.2025. Манифест лежит только в игнорируемом `tmp/acceptance`.
Реальные медицинские данные не использовались. Generated fixture с seed
`20250927` создаётся из кода, а не хранится в Git.

Смысл результата неизменен: `DAILY_REFERRAL_COUNT`, GLOBAL, 7 дней
01–07.04.2025, `weekly_naive`, 2 019 синтетических направлений / 90 дней.
Структурная валидность `VALID` и временная актуальность `STALE` — разные
характеристики. На шести расширяющихся temporal folds (42 пары) MAE выбранной
модели и baseline равна `1.5714285714285714` **направления/день**. Отдельного
финального holdout нет; преимущество ML-кандидата не установлено. Это не
оценка занятости коек, времени ожидания, клинической рекомендации или
качества модели на реальном медицинском наборе.

## API и интерфейс

`GET /api/v1/forecasts/referrals/latest` и `GET /api/v1/forecasts/{id}`
сохраняют старые поля. Добавлены nullable
`validation_period_start: date | null` и
`validation_period_end: date | null`, извлекаемые только из сохранённых
`validation_folds`. Для старых записей без folds — `null`, а не придуманная
дата. Frontend Zod принимает эти поля как optional nullable, поэтому старый
backend не ломает разбор. Карточка показывает forecast ID, GLOBAL scope,
источник, прогнозные даты и значения, MAE и baseline MAE с единицами,
период validation и ограничения. При `STALE` пишет «Историческая проверка
прогноза»; отсутствие прогноза/404 даёт unavailable state без нуля.

Синтетическая подпись включается лишь при
`NEXT_PUBLIC_SYNTHETIC_DEMO=true` **и** `NEXT_PUBLIC_APP_ENV=local|test`.
Для production она выключена. В standalone Next.js эти значения должны быть
переданы **на этапе сборки frontend image**; runtime `.env` не меняет уже
собранные публичные JS chunks. Существующий acceptance launcher задаёт
`NEXT_PUBLIC_APP_ENV=test`, но пока не передаёт build arg
`NEXT_PUBLIC_SYNTHETIC_DEMO=true`. В старом project флаг отсутствует, а
`compose.override.yml` закрепляет прежние image digests и сбрасывает build.
Поэтому требуются новые образы из объединённого checkout и согласование
build arg с владельцем `prepare_acceptance.py`. Не менять environment на
`local` ради подписи и не считать frontend-флаг доказательством provenance:
проверить `manifest.json: dataset=synthetic-only`, delivery manifest и
опубликованные import IDs. Файлы cold-start launcher/readiness принадлежат
второму агенту; параллельно здесь не меняются.

## Инфраструктурный diff для отдельного review

`docker-compose.yml` — **общий base Compose**, а не acceptance-only overlay.
Его MLflow service запускается с явным списком допустимых Host. Это
исправило подтверждённый HTTP 403 `Invalid Host header` для внутреннего
адреса `mlflow:5000`; middleware проверки Host не отключено, host ports не
добавлены. Изменение требует review владельца инфраструктуры перед
интеграцией в общую ветку. Точный фрагмент diff:

```diff
       - --port=5000
+      # MLflow 3 checks Host headers; internal clients address this service as
+      # mlflow:5000. Keep its private DNS name explicit instead of disabling
+      # the host-validation middleware.
+      - --allowed-hosts=mlflow:5000,mlflow,localhost:5000,localhost,127.0.0.1:5000,127.0.0.1
```

Отдельное изменение того же base Compose передаёт
`NEXT_PUBLIC_SYNTHETIC_DEMO` в **development frontend runtime** с default
`false`; production/acceptance build arg определяется `frontend/Dockerfile`
и вызовом сборки. Не объединять эти два механизма в ложный PASS.

## Воспроизведение и проверки

После объединения forecast-кода с независимым cold-start fix использовать
**новый** одноразовый `phase8-*` project с новыми volumes. Подготовка и
bootstrap выполняются скриптами из этого объединённого checkout:
`python -m scripts.operations.prepare_acceptance prepare/start/verify`
и `python -m scripts.acceptance.bootstrap_synthetic --project <project>`.
Их конкретный cold-start порядок и image-security gate остаются у второго
агента. Нельзя подменять их старыми pinned digest из
`phase8-accept-20260926e`. Перед runtime-проверкой записать checkout SHA,
`docker image inspect` IDs только для собственных frontend/backend/worker,
synthetic manifest и фактический forecast ID без env/secrets.

После публикации начальной synthetic fixture сгенерировать отдельный пакет:

```powershell
$projectDir = '<новый проигнорированный каталог phase8-проекта>'
python -m scripts.acceptance.forecast_demo_fixture --project-dir $projectDir
# Затем explicit approve-manifest/import и существующий ml-runner,
# как в FORECAST_DEMO_VERIFICATION.md. Не вставлять прогноз вручную.
python -m scripts.acceptance.verify_forecast_pairs --project-dir $projectDir --expected-mae 1.5714285714285714
```

Точное значение MAE в **новом** project следует сравнить с реальным API;
если состав или даты изменятся, параметр `--expected-mae` должен быть взят
из фактически сохранённого результата, а расхождение — расследовано, не
подогнано. DB verifier запускается read-only в worker с `--forecast-id`
фактически созданной записи. Полные команды для существующего проверенного
project приведены в `FORECAST_DEMO_VERIFICATION.md`, раздел «Воспроизведение».

## Доказательства и открытые пункты для QA

Уже выполнены: настоящий ADMIN OIDC API `latest`/`by-id` → 200 для
forecast ID выше; REGIONAL_ANALYST/HOSPITAL_MANAGER → 404; независимый
пересчёт из SHA-проверенных CSV и первоначальная read-only сверка
PostgreSQL/ClickHouse → 42 пары и та же MAE. Backend: 672 теста,
0 failures, 12 skipped; ML: 18 passed; targeted operations: 4 passed;
import-linter: 12/12. После test-env fix frontend: 123 Vitest tests, lint,
typecheck и production build с `NEXT_PUBLIC_APP_ENV=test`,
`NEXT_PUBLIC_SYNTHETIC_DEMO=true` — PASS.
Новый browser spec успешно обнаруживается через `playwright test --list` при
`MEDSIGNAL_FORECAST_DEMO=1` и исключается из обычного job без этого флага.
Его **выполнение** остаётся NOT TESTED.

**NOT TESTED:** обновлённые backend/frontend образы из этого SHA в
работающем проекте; дополнительные DB verifier assertions
`sum(daily_counts)==rows_loaded` и `forecast.model_version==model.version`;
новые nullable validation даты через реальный API; browser ADMIN
`/dashboard`; browser проверки restricted ролей; независимый повторный
пользовательский маршрут QA. Старый acceptance HTTP endpoint недоступен, а
Docker daemon не отвечал на `docker version`; общий daemon здесь не
перезапускался. Тесты и старые контейнеры не превращают эти пункты в PASS.

Когда обновлённый synthetic project доступен, browser проверка запускается
только по явному opt-in:

```powershell
$env:MEDSIGNAL_FORECAST_DEMO = '1'
$env:MEDSIGNAL_E2E_BASE_URL = 'http://127.0.0.1:<loopback-port>'
$env:MEDSIGNAL_E2E_REALM = '<ignored phase8 project>/realm.json'
cd frontend
npm exec -- playwright test e2e/forecast-demo.spec.ts
```

Тест использует настоящий OIDC и backend, не подменяет ответ. Выводить
секреты realm, Bearer token или полный ответ API в отчёт нельзя.

QA должен проверить на **одном и том же фактическом forecast ID**:
точки и период 01–07.04.2025, GLOBAL, MAE и baseline с единицей,
`validation_period_start/end`, `STALE` и обе подписи; затем проверить 404
для restricted ролей, отсутствие чужих данных после смены доступного
контекста, и маршрут аналитика → прогноз → отдельный сигнал → Copilot
только если последний отдельно включён. `FilterBar` dashboard сейчас
предлагает даты и гранулярность, но не переключение региона/организации;
такой UI-тест не выдумывать. При новом import и model run записать новый
UUID и пересчитать фактические MAE/rows, не переносить старые числа.
