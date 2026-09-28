"""Репозиторий системных операций.

Репозиторий выполняет запросы и не содержит правил (ARCHITECTURE.md, 3.3).
Область данных, где она применима, передаётся явным параметром, а не берётся
из неявного контекста (ADR-0006).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.system import OperationStatus, SystemOperation


class OperationRepository:
    """Доступ к таблице `system_operations`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        operation_type: str,
        request_id: str | None,
        created_at: datetime,
    ) -> SystemOperation:
        operation = SystemOperation(
            id=uuid.uuid4(),
            operation_type=operation_type,
            status=OperationStatus.PENDING,
            request_id=request_id,
            created_at=created_at,
        )
        self._session.add(operation)
        self._session.flush()
        return operation

    def get(self, operation_id: uuid.UUID) -> SystemOperation | None:
        return self._session.get(SystemOperation, operation_id)

    def list_recent(self, *, limit: int) -> list[SystemOperation]:
        statement = (
            select(SystemOperation)
            .order_by(SystemOperation.created_at.desc())
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    def mark_running(
        self, operation_id: uuid.UUID, *, celery_task_id: str | None, at: datetime
    ) -> SystemOperation | None:
        operation = self.get(operation_id)
        if operation is None:
            return None
        operation.status = OperationStatus.RUNNING
        operation.started_at = at
        operation.celery_task_id = celery_task_id
        return operation

    def mark_completed(
        self,
        operation_id: uuid.UUID,
        *,
        result: dict[str, object] | None,
        at: datetime,
    ) -> SystemOperation | None:
        operation = self.get(operation_id)
        if operation is None:
            return None
        operation.status = OperationStatus.COMPLETED
        operation.completed_at = at
        operation.result = result
        return operation

    def mark_failed(
        self, operation_id: uuid.UUID, *, error_summary: str, at: datetime
    ) -> SystemOperation | None:
        operation = self.get(operation_id)
        if operation is None:
            return None
        operation.status = OperationStatus.FAILED
        operation.completed_at = at
        operation.error_summary = error_summary
        return operation
