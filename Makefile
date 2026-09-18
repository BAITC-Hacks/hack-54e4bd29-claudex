# MedSignal — команды разработки.
#
# Все команды выполняются в контейнерах: версии инструментов одинаковы
# у всех разработчиков и в CI.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE      := docker compose
COMPOSE_DEV  := docker compose -f docker-compose.yml -f docker-compose.dev-ports.yml
COMPOSE_PROD := docker compose -f docker-compose.yml -f docker-compose.production.yml
BACKEND_RUN  := $(COMPOSE) run --rm --no-deps backend
API_BASE     := http://localhost/api/v1

.PHONY: help
help: ## Список команд
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Окружение
# ---------------------------------------------------------------------------

.PHONY: env
env: ## Создать .env из .env.example, если его ещё нет
	@if [ -f .env ]; then \
		echo "[medsignal] .env уже существует, оставлен без изменений"; \
	else \
		cp .env.example .env && echo "[medsignal] .env создан"; \
	fi

.PHONY: build
build: ## Собрать образы
	$(COMPOSE) build

.PHONY: config-production
config-production: ## Проверить итоговую production overlay configuration
	$(COMPOSE_PROD) config --quiet

.PHONY: scan-secrets
scan-secrets: ## Проверить Git history и рабочее дерево на секреты (Gitleaks)
	docker run --rm -v "$(CURDIR):/repo" -w /repo zricethezav/gitleaks:v8.30.1 \
		detect --source=/repo --config=/repo/.gitleaks.toml --redact
	@git diff --binary HEAD | docker run --rm -i \
		-v "$(CURDIR):/repo:ro" zricethezav/gitleaks:v8.30.1 \
		detect --pipe --config=/repo/.gitleaks.toml --redact
	@git ls-files --others --exclude-standard | while IFS= read -r file; do cat "$$file"; done \
		| docker run --rm -i -v "$(CURDIR):/repo:ro" \
		zricethezav/gitleaks:v8.30.1 detect --pipe \
		--config=/repo/.gitleaks.toml --redact

.PHONY: up
up: env ## Поднять окружение. Наружу публикуется только порт 80
	$(COMPOSE) up -d --build
	@echo "[medsignal] Frontend: http://localhost"
	@echo "[medsignal] API:      http://localhost/api/v1/health"
	@echo "[medsignal] Keycloak: http://localhost/auth"

.PHONY: up-devtools
up-devtools: env ## Поднять окружение с портами диагностики на 127.0.0.1
	$(COMPOSE_DEV) up -d --build

.PHONY: down
down: ## Остановить окружение, тома сохранить
	$(COMPOSE) down --remove-orphans

.PHONY: clean
clean: ## Остановить окружение и удалить тома вместе с данными
	$(COMPOSE) down --volumes --remove-orphans

.PHONY: logs
logs: ## Логи всех сервисов
	$(COMPOSE) logs -f --tail=100

.PHONY: ps
ps: ## Состояние сервисов
	$(COMPOSE) ps

.PHONY: shell-backend
shell-backend: ## Оболочка в контейнере backend
	$(COMPOSE) exec backend bash

# ---------------------------------------------------------------------------
# Миграции
# ---------------------------------------------------------------------------

.PHONY: migrate
migrate: ## Применить миграции PostgreSQL
	$(COMPOSE) run --rm migrate

.PHONY: migration
migration: ## Создать миграцию: make migration name="описание"
	@if [ -z "$(name)" ]; then \
		echo "[medsignal] Укажите имя: make migration name=\"add_regions\""; exit 1; \
	fi
	$(BACKEND_RUN) alembic revision --autogenerate -m "$(name)"
	@echo "[medsignal] Просмотрите созданную миграцию: автогенерация ошибается"

.PHONY: migrate-down
migrate-down: ## Откатить последнюю миграцию
	$(BACKEND_RUN) alembic downgrade -1

# ---------------------------------------------------------------------------
# Качество
# ---------------------------------------------------------------------------

.PHONY: test
test: test-backend test-ml test-frontend ## Все тесты

.PHONY: test-ml
test-ml: ## Тесты short-horizon forecasting
	docker compose run --rm --no-deps ml-runner python -m pytest /opt/medsignal/ml/tests -q

.PHONY: test-backend
test-backend: ## Тесты backend
	$(COMPOSE) run --rm --no-deps ml-runner \
		python -m pytest /opt/medsignal/backend/tests

.PHONY: test-frontend
test-frontend: ## Тесты frontend
	$(COMPOSE) run --rm --no-deps frontend npm run test

.PHONY: lint
lint: lint-backend lint-frontend lint-imports ## Линтеры, типы и границы модулей

.PHONY: lint-backend
lint-backend: ## Линтер и типы backend
	$(BACKEND_RUN) sh -c "python -m ruff check . && python -m ruff format --check . && python -m mypy app"

.PHONY: lint-frontend
lint-frontend: ## Линтер и типы frontend
	$(COMPOSE) run --rm --no-deps frontend sh -c "npm run lint && npm run typecheck"

.PHONY: lint-imports
lint-imports: ## Проверка архитектурных границ (PHASE 0)
	$(COMPOSE) run --rm --no-deps --volume "$(CURDIR):/repo" \
		--workdir /repo --env PYTHONPATH=/repo:/repo/backend \
		backend lint-imports --config .importlinter

.PHONY: format
format: ## Форматирование backend
	$(BACKEND_RUN) python -m ruff format .

# ---------------------------------------------------------------------------
# Проверка фундамента
# ---------------------------------------------------------------------------

.PHONY: token
token: ## Получить действительный токен Keycloak для проверки
	@bash scripts/dev-token.sh

.PHONY: smoke
smoke: ## Сквозная проверка запущенного окружения
	@bash scripts/smoke-test.sh

.PHONY: health
health: ## Показать health и ready
	@curl -fsS $(API_BASE)/health | python -m json.tool || true
	@curl -sS $(API_BASE)/ready | python -m json.tool || true

# ---------------------------------------------------------------------------
# Data Audit (PHASE 3A)
# ---------------------------------------------------------------------------
# Каталог с выгрузками задаётся снаружи и нигде не зашит в код.
# Источник открывается только на чтение: аудит ничего в нём не меняет.
DATA_DIR ?= $(HOME)/Downloads/data
AUDIT_OUT ?= ./data/audit
AUDIT_DOCS ?= ./docs/data

.PHONY: data-audit
data-audit: ## Разведочный аудит выгрузок: make data-audit DATA_DIR=<каталог>
	python -m data_pipeline.audit.cli \
		--source "$(DATA_DIR)" \
		--output "$(AUDIT_OUT)" \
		--docs "$(AUDIT_DOCS)"

.PHONY: test-audit
test-audit: ## Тесты инструментов Data Audit (на синтетических фикстурах)
	python -m pytest tests/audit -q

.PHONY: lint-audit
lint-audit: ## Линтер, формат и типы конвейера данных
	python -m ruff check data_pipeline tests/audit
	python -m ruff format --check data_pipeline tests/audit
	python -m mypy data_pipeline

.PHONY: deps-audit
deps-audit: ## Установить зависимости Data Audit локально
	python -m pip install --requirement data_pipeline/requirements.txt

# ---------------------------------------------------------------------------
# Конвейер загрузки данных (PHASE 3B)
# ---------------------------------------------------------------------------
# Каталог с выгрузками задаётся снаружи и монтируется только на чтение.
# PIPELINE_RUN поднимает разовый контейнер: постоянного сервиса загрузки нет.
PIPELINE_RUN = DATA_SOURCE_DIR_HOST="$(DATA_DIR)" $(COMPOSE) run --rm pipeline

.PHONY: pipeline-build
pipeline-build: ## Собрать образ исполнителя загрузки
	$(COMPOSE) build pipeline

.PHONY: clickhouse-migrate
clickhouse-migrate: ## Применить схемы ClickHouse
	DATA_SOURCE_DIR_HOST="$(DATA_DIR)" $(COMPOSE) run --rm \
		--entrypoint python pipeline -m app.cli.clickhouse migrate

.PHONY: clickhouse-status
clickhouse-status: ## Состояние схем ClickHouse
	DATA_SOURCE_DIR_HOST="$(DATA_DIR)" $(COMPOSE) run --rm \
		--entrypoint python pipeline -m app.cli.clickhouse status

# ---------------------------------------------------------------------------
# Operations / Phase 8
# ---------------------------------------------------------------------------

PHASE8_BACKUP_DIR ?= ./artifacts/phase8-backup
PHASE8_NAMESPACE ?= phase8-restore

.PHONY: backup
backup: ## Backup PostgreSQL, ClickHouse and MinIO (Redis is non-authoritative)
	python -m scripts.operations.backup --output "$(PHASE8_BACKUP_DIR)"

.PHONY: restore-verify
restore-verify: ## Restore backup only into phase8-* namespaced targets
	python -m scripts.operations.restore_verify --backup "$(PHASE8_BACKUP_DIR)" --namespace "$(PHASE8_NAMESPACE)"

.PHONY: data-discover
data-discover: ## Показать файлы наборов: make data-discover DATA_DIR=<каталог>
	$(PIPELINE_RUN) discover

.PHONY: data-import-referrals
data-import-referrals: ## Загрузить направления
	$(PIPELINE_RUN) import --dataset REFERRALS

.PHONY: data-import-waiting
data-import-waiting: ## Загрузить очередь
	$(PIPELINE_RUN) import --dataset WAITING

.PHONY: data-import-refusals
data-import-refusals: ## Загрузить отказы
	$(PIPELINE_RUN) import --dataset REFUSALS

.PHONY: data-import-treated
data-import-treated: ## Загрузить пролеченные случаи
	$(PIPELINE_RUN) import --dataset TREATED

.PHONY: data-import-core
data-import-core: ## Загрузить все наборы MedSignal Case 1
	$(PIPELINE_RUN) import --all-core

.PHONY: data-dry-run
data-dry-run: ## Холостой прогон по всем наборам, без записи в хранилище
	$(PIPELINE_RUN) import --all-core --dry-run

.PHONY: data-recover
data-recover: ## Отменить незавершённый импорт: make data-recover IMPORT_ID=<uuid>
	$(PIPELINE_RUN) recover --import-id "$(IMPORT_ID)"

# ---------------------------------------------------------------------------
# Short-horizon referral forecasting (PHASE 5A)
# ---------------------------------------------------------------------------

.PHONY: ml-build
ml-build: ## Собрать ML worker/runner image
	$(COMPOSE) build worker ml-runner

.PHONY: ml-train-referrals
ml-train-referrals: ## Обучить кандидатов и сохранить 7-дневный прогноз
	$(COMPOSE) run --rm ml-runner

# ---------------------------------------------------------------------------
# Signal Engine (PHASE 6)
# ---------------------------------------------------------------------------

.PHONY: signal-evaluate
signal-evaluate: ## Выполнить все Signal evaluators и вывести JSON-отчёт
	$(COMPOSE) run --rm backend python -m app.cli.signals evaluate

.PHONY: test-pipeline
test-pipeline: ## Тесты конвейера загрузки (синтетические фикстуры)
	python -m pytest tests/pipeline -q
