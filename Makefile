# MedSignal — команды разработки.
#
# Все команды выполняются в контейнерах: версии инструментов одинаковы
# у всех разработчиков и в CI.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE      := docker compose
COMPOSE_DEV  := docker compose -f docker-compose.yml -f docker-compose.dev-ports.yml
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
test: test-backend test-frontend ## Все тесты

.PHONY: test-backend
test-backend: ## Тесты backend
	$(BACKEND_RUN) python -m pytest

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
