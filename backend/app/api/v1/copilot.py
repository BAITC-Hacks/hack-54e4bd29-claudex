"""Тонкий маршрут Copilot: аутентификация и вызов бизнес-сервиса."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CopilotServiceDep, CurrentUser, RequestIdDep
from app.schemas.common import ERROR_RESPONSES
from app.schemas.copilot import ExplainSignalRequest, ExplainSignalResponse

router = APIRouter(prefix="/copilot", tags=["copilot"], responses=ERROR_RESPONSES)


@router.post(
    "/explain-signal",
    response_model=ExplainSignalResponse,
    summary="Пояснить сигнал по проверенным синтетическим фактам",
    responses={
        502: {"description": "Ответ провайдера не прошёл проверку"},
        504: {"description": "Время ожидания провайдера истекло"},
    },
)
def explain_signal(
    payload: ExplainSignalRequest,
    context: CurrentUser,
    service: CopilotServiceDep,
    request_id: RequestIdDep,
) -> ExplainSignalResponse:
    result = service.explain_signal(context, payload.signal_id, request_id=request_id)
    return ExplainSignalResponse.model_validate(result)
