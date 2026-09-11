"""Зависимости слоя API.

Слой API получает готовые бизнес-сервисы и не создаёт их сам.
Это позволяет подменять сервисы в тестах без обращения к хранилищам.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.business.system.operations import OperationService
from app.core.request_context import get_request_id
from app.database.postgres import session_scope


def get_operation_service() -> OperationService:
    return OperationService(session_scope)


def get_current_request_id(request: Request) -> str | None:
    """Идентификатор текущего запроса.

    Берётся из состояния запроса, а при его отсутствии — из контекста.
    """
    return getattr(request.state, "request_id", None) or get_request_id()


OperationServiceDep = Annotated[OperationService, Depends(get_operation_service)]
RequestIdDep = Annotated[str | None, Depends(get_current_request_id)]
