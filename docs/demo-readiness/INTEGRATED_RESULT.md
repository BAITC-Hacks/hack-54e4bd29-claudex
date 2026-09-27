# Integrated demo result

Дата статической проверки: **2026-09-27**.

## Версия и состав

Объединённый код подготовлен, статические проверки выполнены, runtime ожидает восстановления среды.

- Ветка: `demo/integration` в отдельном managed worktree.
- Проверенный code HEAD: `9de6bde4e96f91beae3926a88501ffb83e478b51`.
- Merge commit forecast + QA/cold-start: `5a8669167ed7f504a36b0c74c4a1f86c30d88ef8`.
- Product/Copilot ancestor: `78ff9fffc0eaee2c01d4568e5b8b9adf84712ab4`.
- Forecast: `6014bd784f8f863f20d08ff731ffc027087a3f26`.
- QA: `e73776be606bae48fe6537ef9d41029752bef4e1`.
- Cold-start fix: `291e8012f20988e89ae6b327886678ff6d39d22a` и `bc140f5e45ae975d842c842b2c023e37ae839618`.
- Integration bridge: `48adc3720c1c93f0f874a4e26aba1d7e0a777bc4` добавляет обязательный frontend build arg `NEXT_PUBLIC_SYNTHETIC_DEMO=true` рядом с уже существующим `NEXT_PUBLIC_APP_ENV=test` и loopback OIDC issuer.
- Readiness review fix: `9de6bde4e96f91beae3926a88501ffb83e478b51` ограничивает общим deadline весь response body read, включая последовательный chunked drip.

`bc140f5` уже содержит QA `e73776b`, оба cold-start commits и общего Copilot ancestor, поэтому QA/Copilot повторно не переносились. Исходные ветки и их worktree не изменялись.

## Дизайн

`DESIGN_INTEGRATION = PENDING`.

Конкретный авторский commit дизайна не передан. В integration HEAD нет самостоятельного design commit; наличие отдельной рабочей ветки без переданного результата не считается интеграцией дизайна.

## Проверка точек пересечения

| Контракт | Фактическое состояние |
| --- | --- |
| ClickHouse readiness | Generated acceptance overlay содержит `clickhouse-ready`: authenticated HTTP `SELECT 1` в сети `data`, bounded body и hard overall deadline для полного read, read-only mount helper. |
| Acceptance verifier | `READY` запрещён при missing/nonzero `clickhouse-ready` или failed migration; штатная команда `python -m app.cli.clickhouse migrate` не заменена. |
| Frontend synthetic build | Launcher теперь передаёт `NEXT_PUBLIC_APP_ENV=test` и `NEXT_PUBLIC_SYNTHETIC_DEMO=true` именно как Docker build args; runtime `.env` не используется как замена build-time embedding. |
| Synthetic label safety | UI включает подпись только при `NEXT_PUBLIC_SYNTHETIC_DEMO=true` и `NEXT_PUBLIC_APP_ENV=local|test`; production не разрешён. Флаг не считается доказательством provenance. |
| Forecast API | Старые поля сохранены; nullable `validation_period_start/end` извлекаются только из сохранённых folds, для старых записей остаются `null`. |
| Forecast card | Сохраняет GLOBAL scope, даты/точки, forecast ID, MAE и baseline MAE с единицей, validation period, `STALE` и честные synthetic/historical ограничения. |
| QA/browser contracts | Обнаружены четыре demo-readiness tests и один отдельный opt-in forecast test; используются настоящий OIDC/backend, без mock authorization. |
| Synthetic fixture | Forecast fixture/verifier включены. Старый forecast UUID и прежние pinned images не переносятся в новый project. Число строк сверяется с фактическими manifests, а не подгоняется под старое ожидание. |

## Статические и локальные проверки без Docker

Среда: Windows, Python 3.12.14 в ignored venv, Node.js 24.14.1, npm 11.11.0. Docker Engine, containers и Compose runtime не использовались.

| Проверка | Результат | Граница результата |
| --- | --- | --- |
| SHA/ancestry и merge-tree | PASS | Forecast и QA/cold расходятся от `78ff9ff`; пересекающихся изменённых путей и merge conflicts не было. |
| Operations pytest | PASS: `178 passed, 1 skipped` | Skip — существующий opt-in PostgreSQL roundtrip, которому нужен isolated Compose project. |
| Backend pytest | PASS: `660 passed, 12 skipped` | Все 12 skips требуют выделенные PostgreSQL/ClickHouse; это не runtime proof. Остались 14 dependency/deprecation warnings. |
| ML pytest | PASS: `18 passed` | Локальные unit/synthetic tests, не новый model run. |
| Frontend Vitest | PASS: `19 files, 123 tests` | Synthetic unit fixtures; не browser runtime. |
| Frontend lint/typecheck | PASS | ESLint exit 0; TypeScript exit 0. |
| Frontend production build | PASS | Build выполнен с `NEXT_PUBLIC_APP_ENV=test`, `NEXT_PUBLIC_SYNTHETIC_DEMO=true` и loopback OIDC issuer; 12/12 static pages generated. |
| Backend Ruff/format/mypy | PASS | Ruff clean, 238 files formatted, mypy clean для 165 source files. |
| ML Ruff/format/mypy | PASS | Ruff clean, 27 files formatted, mypy clean для 27 source files. |
| Integration Python Ruff/format/mypy | PASS | Девять изменённых operations/forecast test/source files clean; четыре source files clean в mypy. |
| Import-linter | PASS: `12 kept, 0 broken` | 283 files / 1541 dependencies; Windows runner запускался с `PYTHONUTF8=1`. |
| Secret scanner | PASS: `3 passed` | Credentials, realm, cookies, tokens и storage state в evidence не сохранялись. |
| Playwright discovery | PASS only as discovery | 4 QA tests и 1 opt-in forecast test перечислены; discovery не считается выполнением. |

Финальное независимое review первоначально нашло Important: одиночный `response.read()` мог превысить общий deadline на последовательных коротких chunk reads. Regression test на настоящем `HTTPResponse` воспроизвёл RED (~156 ms при deadline 70 ms); после `9de6bde` полный read прерывается общим бюджетом, targeted helper `16 passed`, operations `178 passed, 1 skipped`. Оставшийся Minor касается только отсутствующего отдельного `ports` assertion в MLflow-тесте и передан владельцу инфраструктуры вместе с review.

## MLflow base Compose review

Изменение общего `docker-compose.yml` использует точный allowlist:

`mlflow:5000,mlflow,localhost:5000,localhost,127.0.0.1:5000,127.0.0.1`.

Предварительное независимое read-only review не обнаружило Critical/Important: wildcard отсутствует, security middleware не отключён, host ports и новая сеть не добавлены. Minor: `tests/operations/test_mlflow_host_allowlist.py` фиксирует exact allowlist и запрет отключения middleware, но не утверждает отдельно отсутствие `ports`.

`INFRA_OWNER_REVIEW = PENDING` — запрос адресован владельцу У2 / `@Alim-Rakhmet`. До его подтверждения общее изменение base Compose не считается согласованным.

## Runtime и browser status

Docker Engine восстанавливает отдельно назначенный владелец. В этом прогоне Docker не запускался и не перезапускался; чужие containers, volumes и проекты не изменялись.

| Проверка | Статус |
| --- | --- |
| Integrated image build и запись image IDs/build flags | NOT RUN |
| Первый cold start `phase8-demo-integration-*` №1 | NOT RUN |
| Первый cold start нового project №2 | NOT RUN |
| Synthetic bootstrap и scope checks | NOT RUN |
| Forecast fixture approve/import и существующий pipeline run | NOT RUN |
| DB verifier, включая `sum(daily_counts)==rows_loaded` и `forecast.model_version==model.version` | NOT RUN |
| Validation fields через реальный API | NOT RUN |
| Forecast Playwright test | NOT RUN |
| Четыре QA Playwright tests | NOT RUN |

Реально выполненных browser tests: **0**. Skipped/discovery/zero tests не считаются PASS. Платные LLM-вызовы не выполнялись.

## Оставшиеся блокеры и владельцы

| Блокер | Владелец | Критерий снятия |
| --- | --- | --- |
| `P0-ENV`: Docker server API не подтверждён готовым | Назначенный владелец общей среды | Явное подтверждение стабильной доступности Engine; интегратор сам Engine не перезапускает. |
| `INFRA_OWNER_REVIEW = PENDING` | У2 / `@Alim-Rakhmet` | Review точечного MLflow allowlist без wildcard/disable/widening. |
| `DESIGN_INTEGRATION = PENDING` | Автор дизайна | Передан конкретный commit; после объединения повторены затронутые проверки. |
| Integrated runtime evidence отсутствует | Интегратор после environment-ready signal | Два последовательных clean cold start, manifests/image IDs, bootstrap/scope, forecast DB/API verification и 5 реально выполненных browser tests. |

После расширения истории старые PASS не переносятся автоматически. Runtime будет выполняться только в новых собственных `phase8-demo-integration-*` projects; ожидаемые counts, forecast UUID, MAE и даты должны быть сверены с фактически опубликованными manifests и сохранённым pipeline result без изменения модели, provenance или assertions.
