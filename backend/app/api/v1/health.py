"""Эндпоинты здоровья и готовности.

Разделение принципиально:

* `/health` — liveness. Отвечает без обращения к зависимостям и означает,
  что процесс жив. Оркестратор перезапускает контейнер по этой проверке,
  поэтому она не должна падать из-за недоступности базы.
* `/ready` — readiness. Проверяет обязательные зависимости с коротким
  пределом времени и определяет, можно ли направлять трафик.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.database.health import collect_dependency_reports, is_ready
from app.schemas.system import DependencyStatus, HealthResponse, ReadinessResponse

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка живости процесса",
    description="Не обращается к зависимостям. Отвечает 200, пока процесс жив.",
)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Проверка готовности принимать трафик",
    description=(
        "Проверяет зависимости с коротким пределом времени. "
        "Код 503, если хотя бы одна обязательная зависимость недоступна."
    ),
    responses={503: {"model": ReadinessResponse, "description": "Не готов"}},
)
def ready(response: Response) -> ReadinessResponse:
    settings = get_settings()
    reports = collect_dependency_reports()
    ready_now = is_ready(reports)

    if not ready_now:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if ready_now else "not_ready",
        service=settings.app_name,
        version=settings.app_version,
        dependencies=[
            DependencyStatus(
                name=report.name,
                status=report.status,
                required=report.required,
                latency_ms=report.latency_ms,
                reason=report.reason,
            )
            for report in reports
        ],
    )
