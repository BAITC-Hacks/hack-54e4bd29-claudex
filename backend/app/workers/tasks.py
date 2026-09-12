"""Задачи воркера.

PHASE 1 содержит одну техническую задачу, проверяющую сквозной путь:
API регистрирует операцию → ставит задачу → воркер обновляет состояние
транзакционно (ADR-0010). Прикладных задач здесь нет намеренно.

Задача не содержит бизнес-правил: она вызывает тот же сервис, что и API.
Это исключает расхождение поведения между синхронным и фоновым путями.
"""

from __future__ import annotations

import uuid
from typing import Any

from celery import Task

from app.business.system.operations import OperationService
from app.core.logging import get_logger
from app.repositories.unit_of_work import create_unit_of_work
from app.workers.celery_app import REQUEST_ID_TASK_HEADER, celery_app

logger = get_logger(__name__)

PING_OPERATION_TYPE = "system.ping"


def _operation_service() -> OperationService:
    return OperationService(create_unit_of_work)


@celery_app.task(
    name="system.ping",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    acks_late=True,
)
def ping(self: Task, operation_id: str) -> dict[str, Any]:
    """Техническая проверка работоспособности воркера.

    Демонстрирует обязательный жизненный цикл операции:
    PENDING (создано API) → RUNNING → COMPLETED либо FAILED.
    """
    service = _operation_service()
    parsed_id = uuid.UUID(operation_id)

    service.mark_running(parsed_id, celery_task_id=self.request.id)
    try:
        result: dict[str, Any] = {
            "pong": True,
            "worker_hostname": self.request.hostname,
        }
        service.mark_completed(parsed_id, result=result)
        return result
    except Exception as exc:
        # Отказ фиксируется как состояние, а не только как исключение:
        # операция, оставшаяся в RUNNING навсегда, — дефект (ADR-0010).
        logger.error("Задача ping прервана", exc_info=exc)
        service.mark_failed(parsed_id, reason="Техническая задача не выполнена")
        raise


def enqueue_ping(operation_id: uuid.UUID, request_id: str | None) -> str | None:
    """Поставить задачу в очередь после фиксации записи об операции.

    Порядок обязателен: сначала запись в PostgreSQL, затем очередь.
    """
    headers: dict[str, str] = {REQUEST_ID_TASK_HEADER: request_id} if request_id else {}
    async_result = ping.apply_async(args=(str(operation_id),), headers=headers)
    task_id: str | None = async_result.id
    return task_id
