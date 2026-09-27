# Проверка демонстрационного прогноза направлений

Проверено 27.09.2026 в отдельной локальной ветке `feature/demo-forecast-validation`,
созданной от `78ff9fffc0eaee2c01d4568e5b8b9adf84712ab4`
(`feature/copilot-signal-explanation`). Ветка зависит от предыдущей ветки Copilot;
старый `main` не использовался. Публикация, PR и deployment не выполнялись.

## Среда и происхождение данных

Использован только локальный Compose project `phase8-accept-20260926e` с
`manifest.json: dataset=synthetic-only`, loopback HTTP и тестовым Keycloak.
Исходные медицинские выгрузки и production volumes не использовались.

Первоначальная поставка имела 30 вымышленных направлений только за 1–2 января
2025 года. `GET /api/v1/forecasts/referrals/latest` с тестовым ADMIN token
возвращал **404**: истории недостаточно для минимального 42-дневного окна
обучения и последующей временной проверки. Поэтому создана отдельная поставка
`scripts/acceptance/forecast_demo_fixture.py` с фиксированным seed `20250927`:
1 989 вымышленных направлений за 03.01–31.03.2025. Манифест и SHA-256
проверены, поставка явно одобрена и опубликована через существующий
data pipeline: прочитано 1 989, загружено 1 989, отклонено 0. Обе поставки
вместе дают **2 019 записей / 90 полных дней**. Новые файлы создаются только
в игнорируемом `tmp/acceptance/.../source-forecast`; исходный набор
`source-empty` не перезаписывается.

Прогнозируемая величина — `DAILY_REFERRAL_COUNT`, **количество
зарегистрированных направлений за день**. Источник временного ряда — только
опубликованные `fact_referral_events`, сгруппированные по
`toDate(registration_dt)`. Это **GLOBAL** ряд; организация и регион не
назначаются искусственно. Направления не являются занятостью коек, временем
ожидания, датой выписки или доказательством перегрузки.

## Обучение, проверка и результат

Запущен существующий `ml-runner`; готовые predictions/MAE в БД не вставлялись.
Результат сохранён в PostgreSQL, модель зарегистрирована в MLflow.

| Поле | Фактическое значение |
|---|---|
| Forecast ID | `f89d1fd5-2f20-4810-9491-4f42aa2e3ed1` |
| Версия | `referrals-global-20250331-1d4af1ba` |
| Выбранная модель | `weekly_naive` — baseline победил; преимущества ML-кандидата не установлено |
| Сильнейший baseline | `weekly_naive` |
| Обучающие данные для финального прогноза | 01.01–31.03.2025, 90 дней; cutoff 31.03.2025 |
| Проверка | expanding-window rolling origin, 6 непересекающихся 7-дневных validation окон, 42 пары |
| Первое окно | train до 11.02.2025, validation с 12.02.2025 |
| Последнее validation окно | заканчивается 25.03.2025 |
| MAE выбранной модели | **1,5714285714 направления/день** |
| MAE baseline | **1,5714285714 направления/день** на тех же 42 точках |
| Горизонт и даты | 7 дней, 01.04–07.04.2025 |
| Структурный статус / актуальность | `VALID` / `STALE` |

Отдельного финального holdout test здесь **нет**. MAE — среднее
`abs(observed_daily_count - predicted_daily_count)` по validation точкам,
не ошибка на финальной обучающей выборке, не «процент точности» и не
оценка на реальных медицинских данных. Каждая validation дата позже train cutoff
своего fold. Для `weekly_naive` в 7-дневном окне используются значения
предыдущей недели, полностью находящиеся до начала окна. Последние дни марта,
не попавшие в полные validation folds, участвуют только в финальном обучении.

Независимый пересчёт 42 пар из двух синтетических CSV с проверкой их manifest
hash дал **точно 1,5714285714**, совпадая с MAE, полученной через реальный
API. Дополнительно read-only verifier в работающем worker прочитал
опубликованные агрегаты ClickHouse и сохранённые `validation_folds`/метрики
PostgreSQL для этого же forecast ID: 2 019 строк, 90 дней, 6 fold,
42 пары, тот же MAE для выбранной модели и baseline, train cutoff раньше
каждого validation окна. **Обе независимые проверки PASS** на момент запуска.
Позже verifier дополнен проверками равенства числа опубликованных строк
и суммы дневных агрегатов, а также равенства версии прогноза версии модели.
Эти два новых утверждения в работающем контейнере **NOT TESTED** из-за
недоступности Docker daemon; не следует приписывать их предыдущему запуску.
Это проверка
синтетической fixture, не доказательство точности на реальных данных.

## API, область доступа и интерфейс

Через настоящий тестовый Keycloak token получено:

| Проверка | Результат |
|---|---|
| ADMIN `GET /api/v1/forecasts/referrals/latest` | **200**, ID и метрики из таблицы, 7 сохранённых точек |
| ADMIN `GET /api/v1/forecasts/{id}` | **200**, тот же ID |
| REGIONAL_ANALYST latest | **404** |
| HOSPITAL_MANAGER latest | **404** |

`STALE` означает, что дата последней прогнозной точки уже прошла; она **не**
делает сохранённый исторический расчёт недействительным. `generated_at`
27.09.2026 — время запуска, а **не** прогнозируемый период.

Компонент `/dashboard` читает latest через backend, показывает forecast ID,
сохранённые прогнозные даты и значения, источник, глобальную область,
единицы MAE, MAE baseline, временной период validation и ограничения.
Backend добавляет nullable `validation_period_start/end` из сохранённых folds;
для старого результата без folds UI пишет «не указан», не ноль. Для старого
API эти поля в текущем frontend остаются optional. При `STALE` используется
подпись «Историческая проверка прогноза» с пояснением, что MAE получена на
предшествующих окнах. Надпись «Прогноз на синтетических демонстрационных
данных» включается только явным флагом
`NEXT_PUBLIC_SYNTHETIC_DEMO=true` вместе с `NEXT_PUBLIC_APP_ENV=local`
или `NEXT_PUBLIC_APP_ENV=test`
(при сборке standalone-образа или в локальном dev server); по умолчанию
demo-флаг `false`.

**Текущий запущенный frontend контейнер собран до этих изменений.**
Unit tests и локальная production Next.js сборка прошли; browser-проверка
обновлённого UI против этого forecast ID — **NOT TESTED** до обновления
только изолированного demo frontend. Наличие правильного API само по себе
не считается browser PASS. Обычные аналитические фильтры dashboard не
расширяют глобальный forecast на чужую организацию: restricted scopes
получают 404. Текущий `FilterBar` dashboard меняет только даты и
группировку; переключения региона/организации в нём нет. Поэтому поведение
карточки после такого переключения в браузере **NOT TESTED**. GLOBAL
прогноз нельзя подписывать как прогноз выбранной организации.

## Технический блокер, найденный при запуске

MLflow 3.16.1 первоначально отклонил обращение runner к `mlflow:5000`
с HTTP 403 `Invalid Host header`. Проверено отдельно: `Host: mlflow`
получал 404 для несуществующего эксперимента, а `Host: mlflow:5000` — 403.
В Compose добавлен точный private host allowlist с обоими вариантами.
Host-validation middleware, CORS и сетевые границы не отключались. После
адресного пересоздания только synthetic MLflow `Host: mlflow:5000` перестал
давать 403, и существующее обучение завершилось с persisted forecast ID.

Позже Docker Desktop daemon стал возвращать 500 на собственный API и
HTTP-стенд перестал отвечать. После согласованного перезапуска удалось
выполнить прямую сверку PostgreSQL/ClickHouse, но новая browser-проверка
обновлённой карточки остаётся не завершённой. Это не отменяет уже полученные
200/404 и успешный MLflow run. Production image-security gate не менялся.

## Проверки кода и незакрытые проверки стенда

До изменения условия подписи для `test` выполнены: backend pytest — 660 passed, 12 skipped
(изолированные DB integration tests требуют отдельного стенда); ML pytest —
18 passed; targeted operations — 4 passed; frontend Vitest — 122 passed;
frontend lint/typecheck/production build — PASS; Ruff check/format и mypy для
изменённых Python файлов — PASS; import-linter — 12 kept, 0 broken.
Отдельный read-only пересчёт из файлов, сверенных с SHA-256 в synthetic
manifest, повторно дал 42 пары и MAE 1,5714285714.

После этих запусков Docker daemon не ответил даже на `docker version`.
Обновлённый контейнер API, новый browser UI и два дополнительных утверждения
DB verifier остаются **NOT TESTED**. Прямой OIDC API 200/404 и первоначальная
сверка PostgreSQL/ClickHouse были выполнены раньше, до отказа daemon.

При подготовке интеграции выявлено отдельное ограничение конфигурации:
существующий synthetic acceptance project имеет `NEXT_PUBLIC_APP_ENV=test`,
но не задаёт `NEXT_PUBLIC_SYNTHETIC_DEMO`; его overlay закрепляет старые
frontend/backend image digests и не собирает образы. Поэтому он не доказывает
поведение обновлённых API/UI. Условие подписи расширено только на явно
синтетический `test` build; `production` при том же флаге остаётся без
подписи. Для новой изолированной сборки нужно явно передать build arg
`NEXT_PUBLIC_SYNTHETIC_DEMO=true` в frontend и подтвердить происхождение
данных по synthetic manifest. Один лишь browser-флаг происхождение не
подтверждает. Эти runtime-проверки пока **NOT TESTED**.

После исправления условия подписи: Vitest — 123 passed (19 файлов), lint,
typecheck и production Next.js build с `NEXT_PUBLIC_APP_ENV=test` и
`NEXT_PUBLIC_SYNTHETIC_DEMO=true` — PASS. Browser/API status от этих локальных
проверок не меняется. Подробная передача интеграции:
[`FORECAST_INTEGRATION_HANDOFF.md`](FORECAST_INTEGRATION_HANDOFF.md).

## Воспроизведение

Запускать **только** после подготовки отдельного synthetic-only phase8
project, без монтирования `~/Downloads/data`. Новый source каталог должен
быть пустым:

```powershell
$project = 'phase8-accept-20260926e'
$acceptance = Join-Path $env:USERPROFILE "govtech_case1\tmp\medsignal-single-agent\tmp\acceptance\$project"
$compose = @('--project-name', $project, '--env-file', (Join-Path $acceptance '.env'), '--file', (Join-Path (Get-Location).Path 'docker-compose.yml'), '--file', (Join-Path $acceptance 'compose.override.yml'))
python -m scripts.acceptance.forecast_demo_fixture --project-dir $acceptance
$env:DATA_SOURCE_DIR_HOST = Join-Path $acceptance 'source-forecast'
docker compose @compose run --rm --no-deps pipeline approve-manifest --manifest /data/source/manifest-REFERRALS-forecast-demo.json --actor phase8-synthetic-owner --evidence-ref phase8-forecast-validation-v1
docker compose @compose run --rm --no-deps pipeline import --dataset REFERRALS --manifest /data/source/manifest-REFERRALS-forecast-demo.json
Remove-Item Env:DATA_SOURCE_DIR_HOST
docker compose @compose up --no-deps --no-build -d mlflow
docker compose @compose run --rm --no-deps ml-runner
python -m scripts.acceptance.verify_forecast_pairs --project-dir $acceptance --expected-mae 1.5714285714285714
Get-Content scripts/acceptance/verify_forecast_pairs.py -Raw -Encoding UTF8 | docker exec -i "$project-worker-1" python - --forecast-id f89d1fd5-2f20-4810-9491-4f42aa2e3ed1
```

Повторная генерация fixture намеренно отказывается перезаписывать файл.
Повторный запуск `ml-runner` создаёт **новую** версию, а не тот же UUID.
Точный способ запуска Compose описан в
[`scripts/acceptance/bootstrap_synthetic.py`](../../scripts/acceptance/bootstrap_synthetic.py)
и [`docs/acceptance/SYNTHETIC_ANALYTICS_RUNTIME.md`](SYNTHETIC_ANALYTICS_RUNTIME.md).

## Предпоказ и ограничения

Тестовый вход → синтетическая аналитика → глобальный исторический прогноз с
MAE и baseline → отдельный signal, сформированный правилом → уже реализованный
Copilot explain-signal. Copilot надо включить отдельно перед согласованным
live-показом; новых платных вызовов в этой задаче **не было**. Сигнал не
является автоматическим следствием этого прогноза. Результат нельзя
представлять как качество на медицинском датасете или актуальный прогноз
сентября 2026 года.
