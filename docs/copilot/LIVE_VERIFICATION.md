# Локальная live-проверка Copilot (только synthetic acceptance)

Цель — проверить `POST /api/v1/copilot/explain-signal` через настоящий Keycloak token и backend, а не прямой вызов OpenAI. Платный вызов выполняется только после отдельного подтверждения. Не используйте обычный `medsignal` Compose project: в нём могут находиться реальные данные.

Из worktree `tmp/medsignal-copilot` запустите PowerShell:

```powershell
./scripts/copilot/launch-synthetic.ps1 -AcceptanceDir 'C:\Users\zhasy\govtech_case1\tmp\medsignal-single-agent\tmp\acceptance\phase8-accept-20260926e'
```

Скрипт принимает `LLM_API_KEY` скрытым вводом, включает Copilot **только** в backend изолированного `phase8-*` project и монтирует код этой ветки в `/app` только на чтение. Настройки `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4.1-mini-2025-04-14`, `LLM_TIMEOUT_SECONDS=30`, `LLM_MAX_OUTPUT_TOKENS=1200` задаются в памяти процесса. Ключ не записывается в файлы проекта, команды или отчёт. Скрипт не выполняет запрос к модели.

Локальное исключение для удобства: можно передать `-CopilotEnvPath 'C:\путь\вне\репозитория\copilot.env'`. Файл должен находиться **вне Git-репозитория и Docker build context**, иметь ограниченный доступ средствами ОС и содержать только одну строку `LLM_API_KEY=<значение>`. Launcher читает её как буквальный текст, не исполняет как PowerShell, не принимает другие настройки и удаляет ключ из своего окружения после запуска. Этот вариант не отменяет прежний запрет хранить ключ в репозитории, обычном `.env`, Docker image, логах или отчётах. Сам факт наличия файла не разрешает платный запрос.

Проверка без платного вызова:

```powershell
& 'C:\Users\zhasy\govtech_case1\.venv-phase4\Scripts\python.exe' -m scripts.copilot.verify_live --project-dir 'C:\Users\zhasy\govtech_case1\tmp\medsignal-single-agent\tmp\acceptance\phase8-accept-20260926e'
```

Она получает настоящий test token у Keycloak, выбирает **существующий** `SYNTHETIC_DEV_SEED` сигнал с подтверждёнными факторами и проверяет наличие endpoint; LLM не вызывается. После явного согласия на платный тест оператор добавляет `--paid-test`: выполняется ровно **один** запрос через FastAPI, без retry. Проверяющий скрипт печатает только HTTP status, длительность, request_id, названия provider/model, результаты проверки схемы/fact_ids/фактов/ограничений и количество токенов, если они доступны в структурированном backend log. Полный prompt, LLM-текст, токены доступа и credentials не печатаются и не сохраняются.

После теста вернуть synthetic backend к исходной конфигурации без ключа:

```powershell
./scripts/copilot/launch-synthetic.ps1 -AcceptanceDir 'C:\Users\zhasy\govtech_case1\tmp\medsignal-single-agent\tmp\acceptance\phase8-accept-20260926e' -Restore
```

Вызов модели не входит в CI. При `COPILOT_PROVIDER_UNAVAILABLE` сначала отдельно проверить key/quota/model access; модель не заменяется автоматически. API-контракт, карта ошибок и правила для будущего UI — [API_V1.md](API_V1.md).

Результат текущего ограниченного цикла (три HTTP попытки, без успешного `200`) — [LIVE_VERIFICATION_RESULT.md](LIVE_VERIFICATION_RESULT.md). Новый платный цикл требует отдельного решения; `--paid-test` не запускается автоматически.
