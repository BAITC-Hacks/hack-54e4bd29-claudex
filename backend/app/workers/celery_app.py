"""Приложение Celery.

Очереди разделены по типу нагрузки (ADR-0004): обучение модели не должно
блокировать импорт и быстрые операции. В PHASE 1 используется только
очередь `default`; остальные объявлены заранее, чтобы маршрутизация задач
не менялась при их появлении.
"""

from __future__ import annotations

from typing import Any

from celery import Celery
from celery.signals import setup_logging, task_postrun, task_prerun

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.request_context import reset_request_id, sanitize_request_id, set_request_id

# Заголовок, которым request_id переносится из HTTP-запроса в задачу.
REQUEST_ID_TASK_HEADER = "medsignal_request_id"

_request_id_tokens: dict[str, Any] = {}


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(settings.app_name)

    app.conf.update(
        broker_url=settings.celery_broker_url,
        result_backend=settings.celery_result_backend,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        # Повторная выдача задачи при потере воркера безопасна только
        # для идемпотентных задач — это требование ADR-0004.
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_soft_time_limit=settings.celery_task_soft_time_limit_s,
        task_time_limit=settings.celery_task_time_limit_s,
        result_expires=3600,
        broker_connection_retry_on_startup=True,
        task_default_queue="default",
        task_routes={
            "system.*": {"queue": "default"},
            "ingestion.*": {"queue": "ingestion"},
            "ml.*": {"queue": "ml"},
            "simulation.*": {"queue": "simulation"},
            "signals.*": {"queue": "default"},
        },
    )

    # Без force=True: обнаружение задач откладывается до готовности
    # воркера. Немедленный поиск импортировал бы app.workers.tasks
    # прямо во время инициализации этого модуля и дал бы цикл.
    app.autodiscover_tasks(["app.workers"])
    return app


celery_app = create_celery_app()


@setup_logging.connect
def _configure_worker_logging(**_: Any) -> None:
    """Единый формат журнала в воркере и в API."""
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        service=f"{settings.app_name}-worker",
        environment=settings.app_env.value,
    )


@task_prerun.connect
def _bind_request_id(task_id: str | None = None, task: Any = None, **_: Any) -> None:
    """Восстановить request_id из заголовков задачи.

    Позволяет проследить операцию от HTTP-запроса до фоновой части
    по одному идентификатору.
    """
    raw = None
    request = getattr(task, "request", None)
    if request is not None:
        headers = getattr(request, "headers", None) or {}
        raw = headers.get(REQUEST_ID_TASK_HEADER)
    if task_id:
        _request_id_tokens[task_id] = set_request_id(sanitize_request_id(raw))


@task_postrun.connect
def _unbind_request_id(task_id: str | None = None, **_: Any) -> None:
    token = _request_id_tokens.pop(task_id, None) if task_id else None
    if token is not None:
        reset_request_id(token)
