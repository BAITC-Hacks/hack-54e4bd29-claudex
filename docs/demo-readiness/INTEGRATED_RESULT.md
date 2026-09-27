# Integrated demo result

Дата статической проверки: **2026-09-28**.

`ENGINE = AVAILABLE`.

## Повторная browser-проверка и cold start на согласованном UI-контракте

Финальный локальный test/report HEAD: `224fb4f3e65dc571da99bb2043c744a78d6845e7`.
Свежий runtime был собран из `af38340a9c3f4ac8ed8f2ad60b771398adec8fab`;
последующий commit `224fb4f3e65dc571da99bb2043c744a78d6845e7` меняет только
Playwright-синхронизацию admin journey, поэтому application source между этими
точками не менялся. Ветка не сбрасывалась, push/main merge/deployment не
выполнялись.

Локальные commits этого прохода:

- `4d4d81a1a1c38bd901a0a631f1d7ece6e1d28a0f` — согласованные текущие UI labels;
- `694107d60d76029cc1f2cb5cbecafee92049f5ba` — web-first navigation и реальный
  OIDC reload/deep-link scope test;
- `911a569d43c3bcc003f4ba6f9c91f13a85da518d`,
  `dc4842fe3db202a202887e5e58a43f4704d14cec`,
  `f22f2b93de1296011b2ba52cafa80d03ede6d9ad` — минимальный подтверждённый
  frontend fix: dashboard filters сохраняются в URL/history без гонки двух
  `router.replace`; обязательная Next.js Suspense boundary сохранена;
- `af38340a9c3f4ac8ed8f2ad60b771398adec8fab` и
  `224fb4f3e65dc571da99bb2043c744a78d6845e7` — завершённые signal/Copilot,
  forecast, provenance-safe map и responsive admin journey assertions.

### Фактические статусы

- `TEST_CONTRACT_ALIGNMENT = PASS`. Проверены `Сигналы`, доменный статус
  `NEW` с подписью `новый`, `Область: вся система (GLOBAL)`,
  `MedSignal — ситуационный центр` и текущая формулировка исторической
  валидации. Assertions не подгонялись под forecast values.
- `AUTH_RELOAD_AND_DEEP_LINK = PASS` как отдельный targeted run: protected
  `/signals` возвращается после настоящего Keycloak OIDC; hospital-manager после
  полного reload повторно входит через существующую OIDC-сессию на безопасный
  internal route; foreign organization API возвращает `404`, UI показывает
  понятное unavailable-состояние и не раскрывает B1.
- `SIGNAL_ACTION = PASS`: выбран fresh synthetic `NEW`, acknowledge дал `200`,
  `IN_PROGRESS`, `version + 1` и сохранил причину; duplicate action исчез,
  reload + OIDC сохранили состояние; stale card получил `409`.
- `COPILOT_DISABLED = PASS`: реальный backend вернул `503/COPILOT_DISABLED`;
  алгоритмическое объяснение осталось неизменным, повторное открытие не создало
  второй POST, переход к другой карточке не перенёс private state. API key и
  платные LLM-вызовы не использовались.
- `FORECAST_UI = PASS`: отдельный browser test фактически выполнен `1/1` на
  сохранённом forecast `37f6b0d4-0052-4845-9e9b-2705276b3e2a`. Проверены тот же
  API ID, `DAILY_REFERRAL_COUNT`, `GLOBAL`, input/forecast/validation dates,
  MAE модели и baseline в `направлений/день`, семь строк горизонта, historical
  и synthetic limitations. Fixture и pipeline не перезапускались. Прежний
  read-only DB/ClickHouse verifier на неизменённых backend/data остаётся отдельным
  PASS evidence, но в этом проходе повторно не запускался.
- `COLD_START_REPEATABILITY = PASS`: project
  `phase8-demo-integration-repeat-20260928a`, loopback origin
  `http://127.0.0.1:64208`, новые project-prefixed volumes, один первый `start`
  без retry — `READY`; `clickhouse-ready`, PostgreSQL/ClickHouse migrations,
  MinIO identities и runtime verifier прошли. Bootstrap: `30/22/24`, scope:
  admin `[30,22,24]`, hospital/region `[15,11,12]`, disjoint `[0,0,0]`, foreign
  hospital `404`. Project остановлен без `down`; containers/volumes/evidence
  сохранены. Исходный forecast project `...27b` не уничтожался и снова `READY`.
- `BROWSER_SUITE = FAIL`. Единый fresh-project invocation без retries/skip:
  `planned=6`, `passed=4`, `failed=2`, `skipped=0`; exact failures — оба поздних
  restricted-identity OIDC flows. В окне этой серии прогонов Nginx auth zone
  фактически вернул `21` ответ `429`, включая `2` login-action, `2` token и
  Keycloak static font requests.
  Gate не ослаблялся. В разрешённом split все семь сценариев имеют clean
  targeted PASS: четыре QA, admin journey, restricted journey и forecast; это
  не переименовывает combined run в PASS. Для общего PASS требуется отдельное
  infrastructure/security решение по auth-rate orchestration или static
  resources, а не sleep, retry или suppression в тестах.
- `IMAGE_SECURITY = FAIL`. Fresh MinIO scans: server `50 HIGH / 0 CRITICAL`,
  client `44 HIGH / 0 CRITICAL`; signed source, reviewed backport, advisory gate
  и network-isolated CVE probe прошли только для synthetic startup. Известные
  CI findings backend/worker/MLflow остаются по `44 HIGH / 0 CRITICAL`, без
  reported fixed versions. Suppression/allowlist/gate reduction не применялись.
- `SECURITY_ADMISSION = FAIL`. Успешные functional checks и cold start не
  означают production readiness.

Fresh application image IDs: backend
`sha256:acce3e67ec600b159d7d73586dc37a4a3f081fbb9c5280aa3ec0cb87fe398893`,
worker `sha256:3856aaae885d7f3b007cb4d5ab8ba72f4596ba3be96b478fc51dbd7361a124ff`,
MLflow `sha256:a7bd282d480bd1d986c631e98f29254417f1b62c55b27dffdee2717ecb07fbc9`,
frontend `sha256:e4e1ffd9aac6fb01dccf012914c83f439b8d880b4e553e7bc16ed2dbefac285f`,
nginx `sha256:62b51fd2e71a8de9233da70dfe9e2b2d3035867c736e7c64cf87ea2621f7397f`,
pipeline `sha256:ed57dc9fc6fb04a27f5bd720bfd5804a1e21c7494e603cf806460a1463a2564a`.
Source-built MinIO server/client IDs:
`sha256:49ec3981c57e5d8d59931b0c9e988897fbe9a182b78ac071973516d658618dfe`
и `sha256:e61c809e1073c9fc85a41d6fa7b05a4e6cd5e4152322f6aad503c47639ec2bca`.
Frontend собран с `NEXT_PUBLIC_APP_ENV=test`,
`NEXT_PUBLIC_SYNTHETIC_DEMO=true` и project loopback OIDC issuer.

Финальные frontend checks после изменений: Vitest `23 files / 130 tests` PASS,
ESLint PASS, TypeScript PASS, production build PASS (`12/12` pages). Bundled
Playwright Chromium использован вместо system Chrome: системный Chrome загружал
TumarCSP и зависал уже после test PASS на cleanup временного профиля; это
runner/environment limitation, не было скрыто как успешный command exit.

## Актуальная локальная runtime-проверка после переустановки Docker

Проверенный runtime code HEAD: `37261881dbb9dc5f2653e19a35da0af673adaf82`
на ветке `demo/integration` в отдельном worktree. Docker Server `29.8.0`,
context `desktop-linux`. Серверная часть `docker version` отвечает, собственные
images доступны для inspect. Docker повторно не перезапускался, чужие projects и
volumes не изменялись.

Локальные fix commits:

- `a6910b11519112c5625a1385b4a9402d6a135563` — Windows Docker Desktop support
  для signed-source GPG path/socket и fail-closed IAM probe; mobile drawer получил
  отдельное accessible name; forecast E2E locator снова охватывает всю карточку,
  assertions не менялись;
- `37261881dbb9dc5f2653e19a35da0af673adaf82` — `mc` получает `--` перед
  generated secret positional arguments. Это закрывает воспроизведённый случай,
  когда случайный secret начинался с `-` и воспринимался как CLI flag.

### Cold-start история

| Project / SHA | Первый штатный start | Фактический результат |
| --- | --- | --- |
| `phase8-demo-integration-repro-20260927l` / `75f395be336e55bd630a139535060c4efb8e28ed` | один start, без retry | **PASS**: `READY`, migrations и `clickhouse-ready` успешны; security gate остаётся `FAIL`. |
| `phase8-demo-integration-final-20260927a` / `a6910b11519112c5625a1385b4a9402d6a135563` | один start, без retry | **FAIL**: `minio-init` exit 1 на stage `alias`; случайный synthetic secret с ведущим `-` был принят `mc` за flag. Повторный start не выполнялся и результат не переименован в PASS. |
| post-fix `phase8-demo-integration-final-20260927b` / `37261881dbb9dc5f2653e19a35da0af673adaf82` | один start нового project/новых volumes | **PASS**: `READY`; migrations, `clickhouse-ready`, MinIO bootstrap/runtime и четыре scoped identities — PASS. Это отдельная fresh validation после fix, а не retry failed project. |

Failed и завершённый первый projects были остановлены, удалены только их
проверенные project-scoped containers/networks/volumes. Final project `...27b`
оставлен доступным для воспроизводимой проверки.

Final application image IDs: backend
`sha256:91fb024d8097f1642d02df6e505616aa02a111aeef8a8ea7a7c9a05ed8d301af`,
worker `sha256:e56a9827ec8483998126b2e6972b515ab785471f57b08b3cb1c0749b58ef3167`,
MLflow `sha256:3660641f17838c93442bd0efbb0d31ac9b042f73fd8d7e5df5ca74e3cbf1b8c5`,
frontend `sha256:12a329864606608402d1752becfbfb6eebb192e58b5397b5f068ab80366c0c67`,
nginx `sha256:41f17cb10208a12f8195d724e211f9d9c096f9b58e7a01ba806c6eb6245a2f7d`,
pipeline `sha256:b0f98d600194e90bfba34bbea438de68bef15f5a6e296c2891464920975780e3`.
Frontend собран с `NEXT_PUBLIC_APP_ENV=test`,
`NEXT_PUBLIC_SYNTHETIC_DEMO=true` и project loopback OIDC issuer. Project-built
MinIO server/client IDs: `sha256:64e8006d65b20f295205acecad8c2f7e453bf480cda76f42c61bb0ab3fbfc405`
и `sha256:421840f9be603b2b6b21dbc412c22acd991a85f174c91a881f17de0a1b37b25a`.

### Bootstrap, scope и forecast

- Synthetic publication: `REFERRALS=30`, `WAITING=22`, `REFUSALS=24`;
  `TREATED` намеренно не опубликован из-за неподтверждённого reporting period.
- Signed-token scope: admin `[30,22,24]`, hospital manager `[15,11,12]`,
  regional analyst `[15,11,12]`, disjoint intersection `[0,0,0]`, foreign
  hospital `404`, region/organization intersection `[15,11,12]`.
- Forecast fixture: ещё `1 989` invented referral rows; итоговая проверенная
  история `2 019` rows / `90` days. Forecast ID
  `37f6b0d4-0052-4845-9e9b-2705276b3e2a`, модель `weekly_naive`, период
  `2025-04-01`—`2025-04-07`.
- Source и read-only PostgreSQL/ClickHouse verifiers: `6` folds, `42`
  non-overlapping chronological pairs, no leakage, сохранённый/recomputed/baseline
  MAE `1.5714285714285714` referrals/day, `forecast.model_version` совпадает с
  registered model version.
- Реальный forecast browser response прошёл status `200`, schema parse,
  `DAILY_REFERRAL_COUNT`, `GLOBAL`, `STALE`, validation-period и horizon fields,
  затем test остановился на неизменённом text assertion: ожидалось
  `область: глобальная`, фактический UI показывает
  `Область: вся система (GLOBAL)`.

### Browser результаты текущего runtime

Четыре обязательных QA tests реально выполнены: `planned=4`, `passed=0`,
`failed=4`, `skipped=0`. Forecast browser: `planned=1`, `passed=0`, `failed=1`,
`skipped=0`. Assertions не ослаблялись.

| Test | Failing step / actual error | Категория |
| --- | --- | --- |
| Analytics context | После click по организации test не дождался route transition; `page.goBack()` гоняется с незавершённой навигацией и попадает в новый OIDC callback, поэтому field `Конец` отсутствует. | Test navigation synchronization / memory-only auth expectation; analytics API до этого отвечал `200`. |
| Protected routes | Real Keycloak login и возврат на `/signals` успешны; ожидается heading `Лента предупреждений`, фактически согласованный UI содержит `Сигналы`. | Test/design contract mismatch. |
| Hospital scope | Scoped list корректно скрывает B1; прямой `page.goto(foreignPath)` делает full reload и теряет intentionally memory-only token, фактически остаётся пустой Next route announcer вместо ожидаемого error text. | Test auth/navigation expectation; отдельный signed-token verifier подтвердил foreign `404`. |
| Signal action / Copilot disabled | Synthetic source найден, но ожидается exact `Новый`, фактическая доменная подпись — `новый`; state mutation и Copilot step не выполнялись. | Test/UI text mismatch; Copilot runtime assertion остаётся NOT TESTED. |
| Forecast browser | API/schema/validation fields и forecast ID прошли; ожидается `область: глобальная`, фактически `Область: вся система (GLOBAL)`. | Test/UI text mismatch; forecast DB/API PASS, browser FAIL. |

Дополнительно исходный restricted-identity journey — **PASS (1/1)**. Admin journey
после mobile accessibility fix выполнен и остановился на более раннем design-name
расхождении: ожидался link `MedSignal — главная`, фактически
`MedSignal — ситуационный центр`. Полный текущий browser итог с этими двумя
journey runs: `7` tests executed, `1` PASS, `6` FAIL.

### Статические проверки после fixes

- Frontend: Vitest `23 files / 130 tests` PASS; ESLint PASS; TypeScript PASS;
  production build с test/synthetic flags PASS, `12/12` static pages.
- Relevant Python regression: `41 passed, 1 skipped`; skip — отдельный opt-in
  real-MinIO pytest, фактический MinIO runtime/policy probe выполнен отдельно и PASS.
- Ruff check и format check изменённых Python files — PASS.

### Security status и текущие блокеры

`SECURITY_ADMISSION = FAIL`. Известные CI findings не подавлялись: backend,
worker и MLflow — по `44 HIGH / 0 CRITICAL`, одинаковые Debian OS findings без
reported fixed versions. Final MinIO scan: server `50 HIGH / 0 CRITICAL`, client
`44 HIGH / 0 CRITICAL`; advisory gate допускает только synthetic functional
startup, не production admission. Trivy gate, Host validation и остальные
security gates не ослаблялись.

До merge остаются: четыре QA browser failures, forecast browser text-contract
failure, непроверенный Copilot disabled step и открытый image HIGH gate. Успешный
synthetic runtime не означает production readiness. Push, main merge, deployment
и платные LLM-вызовы не выполнялись.

## Версия и состав

Объединённый код и локальные runtime fixes подготовлены; актуальные runtime
результаты приведены выше. Следующие разделы сохраняют историю интеграции и
предыдущих environment-blocked прогонов.

- Ветка: `demo/integration` в отдельном managed worktree.
- Исторический integration/design HEAD: `785a53e40e5328ac2802f16a537f02763e3dcf9d`;
  актуальный runtime code HEAD — `37261881dbb9dc5f2653e19a35da0af673adaf82`.
- Merge commit forecast + QA/cold-start: `5a8669167ed7f504a36b0c74c4a1f86c30d88ef8`.
- Product/Copilot ancestor: `78ff9fffc0eaee2c01d4568e5b8b9adf84712ab4`.
- Forecast: `6014bd784f8f863f20d08ff731ffc027087a3f26`.
- QA: `e73776be606bae48fe6537ef9d41029752bef4e1`.
- Cold-start fix: `291e8012f20988e89ae6b327886678ff6d39d22a` и `bc140f5e45ae975d842c842b2c023e37ae839618`.
- Integration bridge: `48adc3720c1c93f0f874a4e26aba1d7e0a777bc4` добавляет обязательный frontend build arg `NEXT_PUBLIC_SYNTHETIC_DEMO=true` рядом с уже существующим `NEXT_PUBLIC_APP_ENV=test` и loopback OIDC issuer.
- Readiness review fix: `9de6bde4e96f91beae3926a88501ffb83e478b51` ограничивает общим deadline весь response body read, включая последовательный chunked drip.
- MLflow test guard: `2654deb8b6455bc601319a4293a2040629c426a6` отдельно запрещает публикацию host ports сервисом `mlflow`.
- Frontend demo polish: финальный source SHA `aacdc8b753c944eb22557fd1a7f100a5b00e9d94` объединён merge commit `785a53e40e5328ac2802f16a537f02763e3dcf9d`.

`bc140f5` уже содержит QA `e73776b`, оба cold-start commits и общего Copilot ancestor, поэтому QA/Copilot повторно не переносились. Исходные ветки и их worktree не изменялись.

## Дизайн

`DESIGN_INTEGRATION = INCLUDED`.

Финальный handoff агента 3: ветка `feature/frontend-demo-polish`, base `5a8669167ed7f504a36b0c74c4a1f86c30d88ef8`, HEAD `aacdc8b753c944eb22557fd1a7f100a5b00e9d94`, пять frontend-only commits и 32 файла под `frontend/`. Интегратор повторно подтвердил scope, clean merge-tree и объединил exact SHA без конфликтов. На объединённом SHA Vitest `23 files / 130 tests`, lint, typecheck и production build с demo build flags прошли. Защищённый browser runtime не проверен из-за недоступного Engine.

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
| Operations pytest | PASS: `179 passed, 1 skipped` | Skip — существующий opt-in PostgreSQL roundtrip, которому нужен isolated Compose project. |
| Backend pytest | PASS: `660 passed, 12 skipped` | Все 12 skips требуют выделенные PostgreSQL/ClickHouse; это не runtime proof. Остались 14 dependency/deprecation warnings. |
| ML pytest | PASS: `18 passed` | Локальные unit/synthetic tests, не новый model run. |
| Frontend Vitest | PASS: `23 files, 130 tests` | Повторено после включения финального дизайна; synthetic unit fixtures, не browser runtime. |
| Frontend lint/typecheck | PASS | ESLint exit 0; TypeScript exit 0. |
| Frontend production build | PASS | Повторён после дизайна с `NEXT_PUBLIC_APP_ENV=test`, `NEXT_PUBLIC_SYNTHETIC_DEMO=true` и loopback OIDC issuer; 12/12 static pages generated. |
| Backend Ruff/format/mypy | PASS | Ruff clean, 238 files formatted, mypy clean для 165 source files. |
| ML Ruff/format/mypy | PASS | Ruff clean, 27 files formatted, mypy clean для 27 source files. |
| Integration Python Ruff/format/mypy | PASS | Девять изменённых operations/forecast test/source files clean; четыре source files clean в mypy. |
| Import-linter | PASS: `12 kept, 0 broken` | 283 files / 1541 dependencies; Windows runner запускался с `PYTHONUTF8=1`. |
| Secret scanner | PASS: `3 passed` | Credentials, realm, cookies, tokens и storage state в evidence не сохранялись. |
| Playwright discovery | PASS only as discovery | 4 QA tests и 1 opt-in forecast test перечислены; discovery не считается выполнением. |

Независимое AI-review первоначально нашло Important: одиночный `response.read()` мог превысить общий deadline на последовательных коротких chunk reads. Regression test на настоящем `HTTPResponse` воспроизвёл RED (~156 ms при deadline 70 ms); после `9de6bde` полный read прерывается общим бюджетом, targeted helper `16 passed`.

## MLflow base Compose review

### Разрешение владельца проекта

Владелец проекта 2026-09-27 явно разрешил для текущей локальной demo-интеграции изменение общего `docker-compose.yml` только с точным allowlist:

`mlflow:5000,mlflow,localhost:5000,localhost,127.0.0.1:5000,127.0.0.1`.

Разрешение не включает произвольные адреса, wildcard, отключение Host validation, публикацию host ports, изменение сетевых границ или production deployment.

Исторически предыдущая версия отчёта содержала `INFRA_OWNER_REVIEW = PENDING` и ожидание `@Alim-Rakhmet`. Это ожидание снято решением владельца проекта: `@Alim-Rakhmet` не участвовал, review ему не приписывается.

### Техническое AI-review и тесты

Первоначальное независимое read-only review AI-агентом на integration SHA `48adc3720c1c93f0f874a4e26aba1d7e0a777bc4` не обнаружило Critical/Important: exact allowlist соблюдён, wildcard отсутствует, security middleware не отключён, host ports и новая сеть не добавлены. Было одно Minor — отсутствие отдельного тестового assertion для `ports`.

После test-only commit `2654deb8b6455bc601319a4293a2040629c426a6` агент 1 проверил только изменившуюся часть в read-only режиме: Critical/Important/Minor — none. `docker-compose.yml` byte-identical проверенному SHA `48adc3720c1c93f0f874a4e26aba1d7e0a777bc4`, blob `74ca4013eca7bb4f5bfde22aa1e43e7ee4497040`; exact allowlist и запрет отключения middleware не менялись. Это техническое AI-review, не человеческое review.

Новый `test_mlflow_does_not_publish_host_ports` безопасно проверен mutation-run только в памяти: при синтетическом `ports` получен ожидаемый RED, фактический Compose дал `2 passed`; полный operations-набор — `179 passed, 1 skipped`. Предыдущее Minor закрыто.

## Исторический local runtime и browser status до переустановки Docker

Общим Docker управляет только интегратор. В этом статическом прогоне containers не запускались и Docker повторно не перезапускался; чужие containers, volumes и проекты не изменялись.

Ограниченная read-only диагностика после ранее выполненного однократного restart: активный context — `desktop-linux`, но server-часть `docker version` не вернула ответ за 30 секунд. Диагностический CLI после timeout завершён; Docker Desktop/Engine и другие Docker CLI процессы не останавливались. Фактическое состояние: `ENGINE_SERVER_API = UNRESPONSIVE`, поэтому runtime не начат. В пределах текущего разрешения повторный restart, reset, prune и WSL shutdown запрещены; требуется восстановление Engine вне этого прогона либо отдельное решение владельца проекта о следующем recovery-действии.

Разрешённый следующий recovery-цикл остановлен на шаге 2. Preflight повторно подтвердил `wslEngineEnabled=True`, после чего штатный `docker desktop stop --timeout 60` завершился `exit 1` с категорией `context deadline exceeded`; Docker Desktop/backend процессы остались запущены. В соответствии с условием остановки при зависшем Quit команда `wsl --shutdown` не выполнялась, Docker Desktop повторно не запускался, повторный stop/recovery и более сильные действия не предпринимались. Engine recovery: **FAIL AT DESKTOP STOP**.

После того как владелец компьютера вручную отключил и снова запустил Docker Desktop, интегратор выполнил новое bounded-наблюдение без дополнительных restart. Context — `desktop-linux`, Docker Desktop control plane — `running`, но пять последовательных `docker version` server-checks завершились 15-second timeout в пределах суммарного пятиминутного окна. Повторная server-проверка и безопасный image inspect не могли пройти, поэтому `ENGINE_SERVER_API = UNRESPONSIVE`; локальные runtime-попытки остановлены.

После последующей перезагрузки Windows владельцем выполнено отдельное трёхминутное окно наблюдения без Docker restart и WSL shutdown. Пять попыток точной команды `docker version --format '{{.Server.Version}}'`, каждая с 15-second limit, снова завершились категорией `TIMEOUT`; server version не получена. Поэтому подтверждение context после успешного server response, повторный server response и inspect существующего image не выполнялись. Это не `IMAGE_NOT_FOUND`: запрос к Engine не дошёл до стадии image lookup.

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

## Краткий план проверки на другом исправном Docker-хосте

Сам перенос и публикация кода не выполнялись. После отдельного разрешения владельца:

1. Передать локальный commit `54a5642b22eb18440fbbfbdeb131b361a64c7c37` утверждённым способом на заранее доступный исправный Docker-хост; не использовать main, deployment или платные cloud-ресурсы.
2. Проверить exact HEAD, ancestry источников, clean worktree, `docker version` дважды, ожидаемый context и безопасный inspect одного существующего image.
3. Собрать образы из exact checkout с `NEXT_PUBLIC_APP_ENV=test`, `NEXT_PUBLIC_SYNTHETIC_DEMO=true` и согласованным OIDC issuer; записать только image IDs и build flags.
4. Последовательно создать два уникальных `phase8-demo-integration-*` project с отдельными volumes, ports, synthetic accounts и entities. Каждый первый start считать самостоятельным результатом; очищать только ресурсы завершённого собственного project.
5. Выполнить bootstrap/scope, публикацию forecast fixture, существующий pipeline, DB/API verifier, validation fields, четыре QA Playwright tests и один forecast browser test без ослабления assertions/security gates.
6. Обновить этот отчёт фактическими manifests, image IDs, counts и test outcomes без credentials, cookies, storage state, realm contents или реальных данных.

## Исторический VPS preflight до установки Docker, 2026-09-27

`VPS_ENGINE = MISSING` — историческое состояние, снято последующей установкой
rootless Docker владельцем VPS. Актуальный результат приведён ниже.

Закрытый synthetic runtime проверялся на VPS `82.115.43.223` в новой SSH-сессии
пользователя `claudex`, без `sudo` и без системных изменений. Проверенный release
`/home/claudex/medflow-demo/releases/1038995` остаётся на ветке
`demo/integration`, HEAD
`1038995ce9a1a57a85303b31090c71d3108a95eb`, Git status clean.

| Проверка | Фактический результат |
| --- | --- |
| ОС / архитектура | Ubuntu 22.04.5 LTS / x86_64 |
| CPU | 4 logical CPU |
| RAM | 3 911 MiB total / 3 053 MiB available |
| Диск в filesystem домашнего каталога | 67 814 MiB available |
| Порт 8003 | 0 TCP listeners; порт свободен на момент проверки |
| Docker CLI | MISSING: команда отсутствует в новой SSH-сессии; стандартные `/usr/bin`, `/usr/local/bin` и `/snap/bin` не содержат бинарник |
| Docker Engine | MISSING: `/var/run/docker.sock` отсутствует, system service `docker` inactive |
| containerd | system service inactive |
| Compose plugin | MISSING вместе с Docker CLI |
| Доступ `claudex` | группа `docker` отсутствует; пользователь состоит только в ранее существующих группах, права socket не менялись |
| Пакеты Docker | `docker-ce`, `docker-ce-cli`, `docker.io`, `docker-compose-plugin` и `docker-compose-v2` не обнаружены через `dpkg-query` |

Это подтверждённый environment blocker, а не ошибка Compose или приложения:
CLI, daemon socket, daemon service и Compose отсутствуют одновременно. Установка,
изменение групп и прав `docker.sock` не предпринимались. Владелец VPS должен
проверить, что установка выполнялась именно на `82.115.43.223`, завершить установку
Docker Engine и Compose plugin штатным административным способом и предоставить
`claudex` доступ к daemon; после изменения группы требуется новая SSH-сессия.

Независимая локальная проверка текущего acceptance-кода на том же source SHA:
`51 passed` для `test_acceptance_environment.py`, MLflow allowlist, forecast fixture
и forecast-pair verifier. Первый запуск runner дал `31 passed / 20 setup errors`
только из-за запрета записи в стандартный pytest temp; повтор с отдельным
`--basetemp` и отключённым cacheprovider прошёл полностью. Это статическая
проверка launcher/verifier, не VPS runtime evidence.

| Runtime-область | Статус |
| --- | --- |
| Image build и image IDs/build flags | NOT RUN — Docker отсутствует |
| Cold start 1 / cold start 2 | NOT RUN |
| Bootstrap / signed-token scope | NOT RUN |
| Forecast fixture / pipeline / DB / API | NOT RUN |
| QA Playwright / forecast Playwright | 0 реально выполненных tests |
| Design | INCLUDED в source SHA; VPS browser runtime NOT TESTED |
| Copilot | Планируемый режим `COPILOT_ENABLED=false`; VPS disabled-state NOT TESTED, платных вызовов не было |
| `PRIVATE_RUNTIME` | BLOCKED_BY_VPS_DOCKER_MISSING |
| `PUBLIC_ACCESS` | NOT ATTEMPTED; порт 8003, domain proxy, firewall и общий ingress не менялись |
| `SECURITY_ADMISSION` | FAIL; прежние security findings и отсутствие runtime evidence сохраняются |

Локальная ветка отчёта: `feature/vps-demo-runtime`, созданная непосредственно от
проверенного integration HEAD. Удалённый release не менялся, push, registry
publication, main merge и deployment не выполнялись.

## VPS rootless runtime validation, 2026-09-27

`DOCKER_RUNTIME = PASS`, но `PRIVATE_RUNTIME = BLOCKED` до cold start.

Проверка выполнена на `82.115.43.223` в новой SSH-сессии `claudex`, без `sudo`.
Docker Client и Server — `29.8.1`, Compose — `5.5.1`, context — `rootless`.
Engine использует `unix:///run/user/1003/docker.sock`, socket принадлежит UID 1003,
user service активен, security options включают `name=rootless`, Docker root dir —
`/home/claudex/.local/share/docker`. До нашей работы контейнеров и Compose projects
у этого daemon не было; порт 8003 имел 0 listeners и не использовался.

Исходный transferred checkout `1038995ce9a1a57a85303b31090c71d3108a95eb`
был clean. Два минимальных runtime fix выполнены test-first в локальной ветке и
переданы новыми SHA256-verified bundles в отдельные release directories:

- `4b7939478334a79f5e61d97ec67337453f0fb267` — image scan использует
  `timezone.utc` вместо недоступного в Python 3.10 `datetime.UTC`;
- `81317a98209a0a4170273e5d5e765b127f941bdb` — IAM probe в rootless mode
  запускает client как container `0:0`, который отображается на непривилегированного
  владельца rootless daemon и может писать только в bind-mounted probe directory.

Финальный проверявшийся checkout:
`/home/claudex/medflow-demo/releases/81317a9`, ветка
`feature/vps-demo-runtime`, HEAD `81317a98209a0a4170273e5d5e765b127f941bdb`,
Git status clean. Regression evidence: image-scan RED на Python 3.10 import,
затем `10 passed`; rootless IAM RED `1003:1003 != 0:0`, затем `14 passed`;
совместный MinIO/security набор — `55 passed, 1 skipped`.

### Pre-start security gates и images

Patched source-build использовал signed/pinned MinIO tags и существующий
`PATCHED_ACCEPTANCE` contract. Advisory gate — PASS для synthetic functional
acceptance при 10 рассмотренных noncritical advisories. Pinned Trivy `0.58.2`,
DB updated at `2026-09-27 13:06:25 UTC`, обнаружил Go inventory:

| Image | Content ID | Результат |
| --- | --- | --- |
| MinIO server | `sha256:8e4bf689880e8d1afd4e689851aa1aa448ff69868e86bb6b4faeaa4d0444799a` | 50 HIGH / 0 CRITICAL |
| MinIO client | `sha256:bf43dc38f4ab139bdc006e1c78a7fd02f07fa71880c9bf5cf4592bb2e8fc0a8e` | 44 HIGH / 0 CRITICAL |
| Backend | `sha256:6272e6b514a8c840414b63fe1ce23e06646f479e32e165bd3fdc3bda709f7765` | built with target `production`; full application scan NOT RUN |
| Worker | `sha256:967c1bb279ee80aca39866959e1fa446dc8d9db565452bb24c7f8ef43aeb2302` | built with target `production`; full application scan NOT RUN |

MinIO build flags: pinned `linux/amd64`, patched acceptance variant, exact reviewed
source commits and build contract. Frontend image не был построен, поэтому
обязательные build args `NEXT_PUBLIC_APP_ENV=test`,
`NEXT_PUBLIC_SYNTHETIC_DEMO=true` и loopback OIDC issuer ещё не получили runtime
image evidence. MLflow, frontend, nginx и pipeline images также NOT BUILT.

IAM CVE regression на disposable internal network: PASS; limited user и service
account import — DENIED, admin import — ALLOWED, permission unchanged, cleanup —
PASS. Наружные порты, privileged, host network и Docker socket mount не
использовались.

### Подтверждённые resource/pre-start blockers

Rootless Docker хранится под user quota: soft `4096 MiB`, hard `5120 MiB`.
После MinIO gates адресно удалены только два exact reclaimable cache records
нашего build (никаких system/volume/network prune); usage временно снизился до
`2592 MiB`. Штатный последовательный acceptance `prepare` затем успешно собрал
backend и worker, но остановился на следующем по порядку MLflow build с
`AcceptanceCommandError`. На момент остановки quota usage — `4275 MiB`, build
cache — `3.828 GB`, hard limit близок; acceptance directory ещё не создан,
Compose config/start не выполнялись, project containers/volumes/networks — 0.

Отдельно на host отсутствует `setfacl`. Текущий fail-closed launcher требует его,
чтобы дать проверенному non-root Keycloak UID адресный read-доступ к generated
realm, не делая secret world-readable. Пакет не устанавливался, fallback и
permissions не ослаблялись.

Host RAM: 3911 MiB total; минимальное observed available во время builds —
2550 MiB, то есть максимальное наблюдаемое host usage около 1361 MiB. OOM не
наблюдался. Ограничивающим ресурсом стала дисковая quota, не RAM.

| Runtime-область | Актуальный статус |
| --- | --- |
| Cold start 1 / cold start 2 | NOT RUN — prepare blocked до Compose config/start |
| Bootstrap / signed-token scope | NOT RUN |
| Forecast fixture / pipeline / DB / API | NOT RUN; forecast ID и MAE отсутствуют |
| QA Playwright | 0 реально выполненных tests |
| Forecast Playwright | 0 реально выполненных tests |
| Design | INCLUDED в source ancestry; VPS browser runtime NOT TESTED |
| Copilot | `COPILOT_ENABLED=false` запланирован; disabled-state NOT TESTED, `LLM_API_KEY` не задавался |
| `PRIVATE_RUNTIME` | BLOCKED_BY_VPS_QUOTA_AND_ACL_TOOLING |
| `PUBLIC_ACCESS` | NOT ATTEMPTED; 8003, reverse proxy, firewall и ingress не менялись |
| `SECURITY_ADMISSION` | FAIL из-за оставшихся HIGH findings и отсутствия полного runtime evidence |

## Исторические environment-блокеры и владельцы

| Блокер | Владелец | Критерий снятия |
| --- | --- | --- |
| `P0-ENV`: после Windows reboot server API пять раз не ответил за трёхминутное окно | Владелец проекта / другой исправный Docker-хост или отдельное recovery-решение | Engine дважды отвечает на bounded `docker version`, затем проходит безопасный inspect существующего image; локальные recovery-попытки не повторяются автоматически. |
| `P0-VPS-QUOTA`: quota `4096/5120 MiB`, usage `4275 MiB` после только двух из шести app images | Владелец VPS | Увеличить quota для `claudex` либо предоставить согласованный build host/export; затем exact images должны быть собраны и проверены без global prune. |
| `P0-VPS-ACL`: `setfacl` отсутствует | Владелец VPS | Предоставить штатный `acl/setfacl` либо отдельно согласовать и протестировать столь же адресный rootless-safe механизм; realm не должен стать world-readable. |
| Integrated runtime evidence отсутствует | Интегратор после environment-ready signal | Два последовательных clean cold start, manifests/image IDs, bootstrap/scope, forecast DB/API verification и 5 реально выполненных browser tests. |

`SECURITY_ADMISSION` остаётся не-PASS до runtime evidence. После расширения истории старые PASS не переносятся автоматически. Следующий VPS runtime будет выполняться только в новых собственных `phase8-claudex-vps-*` projects; прежнее имя `phase8-demo-integration-*` относится только к локальному плану до переноса. Ожидаемые counts, forecast UUID, MAE и даты должны быть сверены с фактически опубликованными manifests и сохранённым pipeline result без изменения модели, provenance или assertions.
