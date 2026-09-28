"""Общая настройка тестов.

Переменные окружения задаются до первого импорта приложения: настройки
кэшируются на время жизни процесса, и изменить их позже нельзя.

Тесты не требуют работающих PostgreSQL, ClickHouse, Redis и Keycloak.
Внешние зависимости подменяются; проверки, которым нужны реальные сервисы,
помечены маркером `integration`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

# --- Окружение тестов -------------------------------------------------------
# APP_ENV=local разрешает подставной адаптер аутентификации.
# Вне локальной среды он приводит к отказу старта (ADR-0009).
TEST_ENVIRONMENT = {
    "APP_ENV": "local",
    "APP_DEBUG": "false",
    "APP_SECRET": "test-secret-local_dev_only",
    "LOG_LEVEL": "WARNING",
    "LOG_FORMAT": "json",
    "CORS_ALLOWED_ORIGINS": "http://localhost:3000",
    "TRUSTED_HOSTS": "",
    "AUTH_TEST_MODE": "true",
    "OIDC_ISSUER": "http://localhost/auth/realms/medsignal",
    "OIDC_INTERNAL_BASE_URL": "http://keycloak:8080/auth/realms/medsignal",
    "POSTGRES_PASSWORD": "test-local_dev_only",
    "CLICKHOUSE_PASSWORD": "test-local_dev_only",
    "REDIS_PASSWORD": "test-local_dev_only",
    "MINIO_ACCESS_KEY": "test-local_dev_only",
    "MINIO_SECRET_KEY": "test-local_dev_only",
    "METRICS_ENABLED": "false",
}

# Значения назначаются, а не дополняются: набор тестов задаёт своё окружение
# сам. Иначе результат зависит от переменных, унаследованных от сервиса или
# от оболочки разработчика, и тесты проходят не везде одинаково.
for _key, _value in TEST_ENVIRONMENT.items():
    # Явно включённые ClickHouse integration tests должны использовать
    # credentials контейнерного окружения. Обычный pytest по-прежнему
    # полностью изолирован тестовыми значениями.
    if os.getenv("RUN_CLICKHOUSE_INTEGRATION") == "1" and _key.startswith("CLICKHOUSE_"):
        continue
    os.environ[_key] = _value


from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import (  # noqa: E402
    get_operation_service,
    get_security_context,
)
from app.business.system.operations import OperationSnapshot  # noqa: E402
from app.core.exceptions import NotFoundError, UnauthenticatedError  # noqa: E402
from app.models.system import OperationStatus  # noqa: E402
from app.security.context import (  # noqa: E402
    GLOBAL_SCOPE_ROLES,
    DataScope,
    SecurityContext,
)
from app.security.testing import StaticTokenVerifier  # noqa: E402
from tests.fakes import FakeStore, unit_of_work_factory  # noqa: E402


class FakeOperationService:
    """Подмена сервиса операций без обращения к PostgreSQL.

    Повторяет наблюдаемое поведение настоящего сервиса: регистрация
    создаёт запись в PENDING, переходы меняют состояние, неизвестный
    идентификатор приводит к NotFoundError.
    """

    def __init__(self) -> None:
        self.records: dict[uuid.UUID, OperationSnapshot] = {}
        self.enqueue_should_fail = False

    def register(self, *, operation_type: str, request_id: str | None) -> uuid.UUID:
        operation_id = uuid.uuid4()
        self.records[operation_id] = OperationSnapshot(
            id=operation_id,
            operation_type=operation_type,
            status=OperationStatus.PENDING,
            created_at=datetime.now(tz=UTC),
            started_at=None,
            completed_at=None,
            error_summary=None,
            result={"request_id": request_id} if request_id else None,
        )
        return operation_id

    def mark_running(
        self,
        operation_id: uuid.UUID,
        *,
        celery_task_id: str | None = None,  # noqa: ARG002 - как в настоящем сервисе
    ) -> None:
        self._require(operation_id).status = OperationStatus.RUNNING

    def mark_completed(
        self, operation_id: uuid.UUID, *, result: dict[str, Any] | None = None
    ) -> None:
        record = self._require(operation_id)
        record.status = OperationStatus.COMPLETED
        record.result = result

    def mark_failed(self, operation_id: uuid.UUID, *, reason: str) -> None:
        record = self._require(operation_id)
        record.status = OperationStatus.FAILED
        record.error_summary = reason

    def get(self, operation_id: uuid.UUID) -> OperationSnapshot:
        return self._require(operation_id)

    def list_recent(self, *, limit: int = 20) -> list[OperationSnapshot]:
        return list(self.records.values())[:limit]

    def _require(self, operation_id: uuid.UUID) -> OperationSnapshot:
        record = self.records.get(operation_id)
        if record is None:
            raise NotFoundError("Операция не найдена")
        return record


@pytest.fixture
def operation_service() -> FakeOperationService:
    return FakeOperationService()


@pytest.fixture
def store() -> FakeStore:
    """Хранилище предметной области в памяти."""
    return FakeStore()


@pytest.fixture
def uow_factory(store: FakeStore):
    return unit_of_work_factory(store)


class ScopeOverride:
    """Область данных, назначаемая тестом конкретному субъекту токена."""

    def __init__(self) -> None:
        self.by_subject: dict[str, DataScope] = {}
        self.user_ids: dict[str, uuid.UUID] = {}

    def assign(self, subject: str, scope: DataScope, user_id: uuid.UUID) -> None:
        self.by_subject[subject] = scope
        self.user_ids[subject] = user_id


@pytest.fixture
def scopes() -> ScopeOverride:
    return ScopeOverride()


def _build_test_context(scopes: ScopeOverride):
    """Замена зависимости аутентификации без обращения к базе.

    Токен проверяется тем же подставным адаптером, что и в приложении,
    поэтому покрытие «действительный принимается, недействительный
    отклоняется» сохраняется. Из базы берётся только область данных —
    её подставляет тест.
    """
    verifier = StaticTokenVerifier()

    def dependency(request: Request) -> SecurityContext:
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise UnauthenticatedError("Требуется токен доступа")

        claims = verifier.verify(token)
        scope = scopes.by_subject.get(claims.subject, DataScope.unresolved())
        if claims.roles & GLOBAL_SCOPE_ROLES:
            scope = DataScope.global_scope()

        return SecurityContext(
            user_id=claims.subject,
            username=claims.username,
            email=claims.email,
            roles=claims.roles,
            scope=scope,
            token_id=claims.token_id,
            internal_user_id=scopes.user_ids.get(claims.subject, uuid.uuid4()),
        )

    return dependency


@pytest.fixture
def app(
    operation_service: FakeOperationService, scopes: ScopeOverride
) -> Iterator[FastAPI]:
    """Экземпляр приложения с подменёнными внешними зависимостями."""
    from app.main import create_app

    application = create_app()
    application.dependency_overrides[get_operation_service] = lambda: operation_service
    application.dependency_overrides[get_security_context] = _build_test_context(scopes)
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False: проверяем ответ обработчика ошибок,
    # а не всплытие исключения в тест.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def all_dependencies_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """Все зависимости отвечают успешно."""
    from app.database import health

    monkeypatch.setattr(
        health,
        "DEPENDENCY_CHECKS",
        {
            name: (lambda _timeout: None)
            for name in ("postgres", "clickhouse", "redis", "object_storage")
        },
    )
