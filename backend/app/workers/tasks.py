"""Задачи воркера.

Содержит техническую ping-задачу и фоновые прикладные оркестраторы:
API регистрирует операцию → ставит задачу → воркер обновляет состояние
транзакционно (ADR-0010). Прикладных задач здесь нет намеренно.

Задача не содержит бизнес-правил: она вызывает тот же сервис, что и API.
Это исключает расхождение поведения между синхронным и фоновым путями.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from celery import Task

from app.business.ports import UnitOfWorkFactory
from app.business.signals.evaluation import SignalEvaluationService
from app.business.system.operations import OperationService
from app.core.http_metrics import record_background_job
from app.core.logging import get_logger
from app.core.request_context import get_request_id
from app.repositories.unit_of_work import create_unit_of_work
from app.workers.celery_app import REQUEST_ID_TASK_HEADER, celery_app

logger = get_logger(__name__)

PING_OPERATION_TYPE = "system.ping"


def _operation_service() -> OperationService:
    return OperationService(cast(UnitOfWorkFactory, create_unit_of_work))


def _signal_evaluation_service() -> SignalEvaluationService:
    from app.composition import build_signal_evaluation_service

    return build_signal_evaluation_service()


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
        record_background_job("system.ping", "completed")
        return result
    except Exception as exc:
        # Отказ фиксируется как состояние, а не только как исключение:
        # операция, оставшаяся в RUNNING навсегда, — дефект (ADR-0010).
        logger.error("Задача ping прервана", exc_info=exc)
        service.mark_failed(parsed_id, reason="Техническая задача не выполнена")
        record_background_job("system.ping", "failed")
        raise


def enqueue_ping(operation_id: uuid.UUID, request_id: str | None) -> str | None:
    """Поставить задачу в очередь после фиксации записи об операции.

    Порядок обязателен: сначала запись в PostgreSQL, затем очередь.
    """
    headers: dict[str, str] = {REQUEST_ID_TASK_HEADER: request_id} if request_id else {}
    async_result = ping.apply_async(args=(str(operation_id),), headers=headers)
    task_id: str | None = async_result.id
    return task_id


@celery_app.task(
    name="ml.train_referral_forecast",
    acks_late=True,
    soft_time_limit=600,
    time_limit=900,
)
def train_referral_forecast() -> dict[str, str]:
    """Train/evaluate candidates and persist one versioned seven-day forecast."""
    # Lazy import keeps ML dependencies out of the API process and image.
    from app.adapters.forecasting import build_forecast_training_service

    try:
        forecast_id = build_forecast_training_service().run_referral_forecast()
        record_background_job("ml.train_referral_forecast", "completed")
        return {"forecast_id": str(forecast_id)}
    except Exception:
        record_background_job("ml.train_referral_forecast", "failed")
        raise


@celery_app.task(
    name="signals.evaluate",
    bind=True,
    acks_late=True,
    soft_time_limit=600,
    time_limit=900,
)
def evaluate_signals(self: Task, operation_id: str | None = None) -> dict[str, Any]:
    """Evaluate all enabled rules with persistent operation status."""
    operations = _operation_service()
    parsed_id = (
        uuid.UUID(operation_id)
        if operation_id is not None
        else operations.register(
            operation_type="signals.evaluate", request_id=get_request_id()
        )
    )
    operations.mark_running(parsed_id, celery_task_id=self.request.id)
    try:
        report = _signal_evaluation_service().evaluate_all().as_dict()
        operations.mark_completed(parsed_id, result=report)
        record_background_job("signals.evaluate", "completed")
        return {"operation_id": str(parsed_id), "report": report}
    except Exception as exc:
        logger.error(
            "Оценка Signal Engine прервана",
            extra={"operation_id": str(parsed_id)},
            exc_info=exc,
        )
        operations.mark_failed(parsed_id, reason="Signal Engine не завершил оценку")
        record_background_job("signals.evaluate", "failed")
        raise


@celery_app.task(
    name="ml.forecast_organization",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=900,
)
def forecast_organization(
    *,
    hospital_id: str,
    model_version: str,
    mapping_version: str,
    delivery_watermark: str,
    origin: str,
    horizon_days: int = 7,
) -> dict[str, object]:
    """Internal worker command; accepts identifiers, never model policy or paths."""
    from datetime import date

    from app.adapters.organization_forecasting import build_organization_forecast_service
    from app.business.forecasting.contracts import OrganizationForecastRequest

    request = OrganizationForecastRequest(
        hospital_id=uuid.UUID(hospital_id),
        model_version=model_version,
        mapping_version=mapping_version,
        delivery_watermark=delivery_watermark,
        origin=date.fromisoformat(origin),
        horizon_days=horizon_days,
    )
    try:
        result = build_organization_forecast_service().run(request)
        record_background_job("ml.forecast_organization", str(result["status"]).lower())
        return result
    except Exception:
        record_background_job("ml.forecast_organization", "failed")
        raise
