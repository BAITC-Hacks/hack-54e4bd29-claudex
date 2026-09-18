"""Служебные эндпоинты PHASE 1.

Назначение: проверить сквозные механизмы фундамента — проверку токена
Keycloak, построение контекста доступа, постановку фоновой задачи
и устойчивое состояние операции.

Прикладных эндпоинтов здесь нет: домен появляется в PHASE 2.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, OperationServiceDep, RequestIdDep
from app.core.exceptions import DependencyUnavailableError
from app.core.logging import get_logger
from app.models.system import OperationStatus
from app.schemas.common import ERROR_RESPONSES
from app.schemas.system import (
    OperationAccepted,
    OperationResponse,
    SecurityContextResponse,
)
from app.workers.tasks import PING_OPERATION_TYPE, enqueue_ping

logger = get_logger(__name__)

router = APIRouter(prefix="/system", tags=["system"], responses=ERROR_RESPONSES)


@router.get(
    "/whoami",
    response_model=SecurityContextResponse,
    summary="Контекст доступа текущего пользователя",
    description=(
        "Защищённый эндпоинт. Принимает действительный токен Keycloak "
        "и отклоняет недействительный. Область данных в PHASE 1 "
        "не разрешается: таблица областей появляется в PHASE 2."
    ),
)
def whoami(context: CurrentUser) -> SecurityContextResponse:
    return SecurityContextResponse(
        user_id=context.user_id,
        internal_user_id=context.internal_user_id,
        username=context.username,
        roles=sorted(role.value for role in context.roles),
        region_ids=sorted(context.scope.region_ids),
        hospital_ids=sorted(context.scope.hospital_ids),
        has_global_scope=context.has_global_scope,
        scope_resolved=context.scope.resolved,
    )


@router.post(
    "/ping-task",
    response_model=OperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Поставить техническую задачу в очередь",
    description=(
        "Регистрирует операцию в PostgreSQL и ставит задачу в очередь. "
        "Порядок обязателен: сначала запись, затем очередь (ADR-0010)."
    ),
)
def create_ping_task(
    context: CurrentUser,
    service: OperationServiceDep,
    request_id: RequestIdDep,
) -> OperationAccepted:
    operation_id = service.register(
        operation_type=PING_OPERATION_TYPE, request_id=request_id
    )

    try:
        enqueue_ping(operation_id, request_id)
    except Exception as exc:
        # Запись уже существует в статусе PENDING и остаётся видимой.
        # Отказ брокера не приводит к молчаливой потере операции.
        logger.error("Не удалось поставить задачу в очередь", exc_info=exc)
        service.mark_failed(operation_id, reason="Очередь задач недоступна")
        raise DependencyUnavailableError(
            "Очередь задач недоступна, операция не запущена"
        ) from exc

    logger.info(
        "Техническая задача поставлена в очередь",
        extra={"operation_id": str(operation_id), "actor_id": context.user_id},
    )
    return OperationAccepted(operation_id=operation_id, status=OperationStatus.PENDING)


@router.get(
    "/operations/{operation_id}",
    response_model=OperationResponse,
    summary="Состояние долгой операции",
)
def get_operation(
    operation_id: uuid.UUID,
    context: CurrentUser,  # noqa: ARG001 — требуется аутентификация
    service: OperationServiceDep,
) -> OperationResponse:
    snapshot = service.get(operation_id)
    return OperationResponse(
        id=snapshot.id,
        operation_type=snapshot.operation_type,
        status=snapshot.status,
        created_at=snapshot.created_at,
        started_at=snapshot.started_at,
        completed_at=snapshot.completed_at,
        error_summary=snapshot.error_summary,
        result=snapshot.result,
    )
