# Integrated demo result

Дата статической проверки: **2026-09-27**.

`ENGINE = UNRESPONSIVE`.

## Версия и состав

Объединённый код подготовлен, статические проверки выполнены, runtime ожидает восстановления среды.

- Ветка: `demo/integration` в отдельном managed worktree.
- Проверенный code HEAD: `785a53e40e5328ac2802f16a537f02763e3dcf9d`.
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

## Runtime и browser status

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

## VPS runtime preflight, 2026-09-27

`VPS_ENGINE = MISSING`.

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

## Оставшиеся блокеры и владельцы

| Блокер | Владелец | Критерий снятия |
| --- | --- | --- |
| `P0-ENV`: после Windows reboot server API пять раз не ответил за трёхминутное окно | Владелец проекта / другой исправный Docker-хост или отдельное recovery-решение | Engine дважды отвечает на bounded `docker version`, затем проходит безопасный inspect существующего image; локальные recovery-попытки не повторяются автоматически. |
| `P0-VPS-ENV`: на VPS отсутствуют Docker CLI, daemon socket/service, Compose plugin и группа `docker` | Владелец VPS | На `82.115.43.223` в новой SSH-сессии `claudex` Docker client/server и Compose возвращают версии, context подтверждён, user access проходит без изменения socket permissions. |
| Integrated runtime evidence отсутствует | Интегратор после environment-ready signal | Два последовательных clean cold start, manifests/image IDs, bootstrap/scope, forecast DB/API verification и 5 реально выполненных browser tests. |

`SECURITY_ADMISSION` остаётся не-PASS до runtime evidence. После расширения истории старые PASS не переносятся автоматически. Следующий VPS runtime будет выполняться только в новых собственных `phase8-claudex-vps-*` projects; прежнее имя `phase8-demo-integration-*` относится только к локальному плану до переноса. Ожидаемые counts, forecast UUID, MAE и даты должны быть сверены с фактически опубликованными manifests и сохранённым pipeline result без изменения модели, provenance или assertions.
