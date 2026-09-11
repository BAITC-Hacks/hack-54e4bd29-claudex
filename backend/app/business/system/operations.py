"""Жизненный цикл долгих операций (ADR-0010).

Правила, реализуемые здесь:

* Запись создаётся и фиксируется ДО постановки задачи в очередь.
  Обратный порядок допускает старт обработки раньше появления записи.
* Воркер обновляет состояние транзакционно, каждый переход отдельно.
* Отказ фиксируется как состояние, а не только как исключение.
* Краткая причина отказа не содержит внутренних деталей: трассировка
  остаётся в журнале, связанном по `request_id`.

Сервис не знает об HTTP и вызывается одинаково из API и из воркера.
Это исключает расхождение правил между синхронным и фоновым путями.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.system import OperationStatus, SystemOperation
from app.repositories.operations import OperationRepository

logger = get_logger(__name__)

SessionScope = Callable[[], AbstractContextManager[Session]]

# Предел длины причины отказа: сообщение предназначено пользователю,
# а не для переноса содержимого исключения.
MAX_ERROR_SUMMARY_LENGTH = 500


class OperationService:
    """Управление состоянием долгих операций."""

    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    # ------------------------------------------------------------------
    # Регистрация
    # ------------------------------------------------------------------

    def register(self, *, operation_type: str, request_id: str | None) -> uuid.UUID:
        """Создать запись в статусе PENDING и зафиксировать транзакцию.

        Возвращает идентификатор, по которому вызывающая сторона ставит
        задачу в очередь. Порядок важен: сначала запись, потом очередь.
        """
        with self._session_scope() as session:
            repository = OperationRepository(session)
            operation = repository.create(
                operation_type=operation_type,
                request_id=request_id,
                created_at=_utcnow(),
            )
            operation_id = operation.id

        logger.info(
            "Операция зарегистрирована",
            extra={"operation_id": str(operation_id), "operation_type": operation_type},
        )
        return operation_id

    # ------------------------------------------------------------------
    # Переходы состояния
    # ------------------------------------------------------------------

    def mark_running(
        self, operation_id: uuid.UUID, *, celery_task_id: str | None = None
    ) -> None:
        with self._session_scope() as session:
            updated = OperationRepository(session).mark_running(
                operation_id, celery_task_id=celery_task_id, at=_utcnow()
            )
            if updated is None:
                raise NotFoundError("Операция не найдена")
        logger.info("Операция выполняется", extra={"operation_id": str(operation_id)})

    def mark_completed(
        self, operation_id: uuid.UUID, *, result: dict[str, Any] | None = None
    ) -> None:
        with self._session_scope() as session:
            updated = OperationRepository(session).mark_completed(
                operation_id, result=result, at=_utcnow()
            )
            if updated is None:
                raise NotFoundError("Операция не найдена")
        logger.info("Операция завершена", extra={"operation_id": str(operation_id)})

    def mark_failed(self, operation_id: uuid.UUID, *, reason: str) -> None:
        """Зафиксировать отказ.

        Вызывается в обработчике исключения задачи. Операция, оставшаяся
        в статусе RUNNING навсегда, — дефект (ADR-0010).
        """
        summary = reason.strip()[:MAX_ERROR_SUMMARY_LENGTH] or "Операция прервана"
        with self._session_scope() as session:
            updated = OperationRepository(session).mark_failed(
                operation_id, error_summary=summary, at=_utcnow()
            )
            if updated is None:
                raise NotFoundError("Операция не найдена")
        logger.warning(
            "Операция прервана",
            extra={"operation_id": str(operation_id), "error_code": "OPERATION_FAILED"},
        )

    # ------------------------------------------------------------------
    # Чтение
    # ------------------------------------------------------------------

    def get(self, operation_id: uuid.UUID) -> OperationSnapshot:
        with self._session_scope() as session:
            operation = OperationRepository(session).get(operation_id)
            if operation is None:
                raise NotFoundError("Операция не найдена")
            return _to_snapshot(operation)

    def list_recent(self, *, limit: int = 20) -> list[OperationSnapshot]:
        with self._session_scope() as session:
            operations = OperationRepository(session).list_recent(limit=limit)
            return [_to_snapshot(item) for item in operations]


class OperationSnapshot:
    """Состояние операции, отделённое от сессии SQLAlchemy.

    Возврат объекта модели наружу привязал бы вызывающую сторону
    к жизненному циклу сессии.
    """

    __slots__ = (
        "completed_at",
        "created_at",
        "error_summary",
        "id",
        "operation_type",
        "result",
        "started_at",
        "status",
    )

    def __init__(
        self,
        *,
        id: uuid.UUID,  # noqa: A002
        operation_type: str,
        status: OperationStatus,
        created_at: datetime,
        started_at: datetime | None,
        completed_at: datetime | None,
        error_summary: str | None,
        result: dict[str, Any] | None,
    ) -> None:
        self.id = id
        self.operation_type = operation_type
        self.status = status
        self.created_at = created_at
        self.started_at = started_at
        self.completed_at = completed_at
        self.error_summary = error_summary
        self.result = result

    def __iter__(self) -> Iterator[tuple[str, Any]]:
        for name in self.__slots__:
            yield name, getattr(self, name)


def _to_snapshot(operation: SystemOperation) -> OperationSnapshot:
    return OperationSnapshot(
        id=operation.id,
        operation_type=operation.operation_type,
        status=OperationStatus(operation.status),
        created_at=operation.created_at,
        started_at=operation.started_at,
        completed_at=operation.completed_at,
        error_summary=operation.error_summary,
        result=operation.result,
    )


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)
