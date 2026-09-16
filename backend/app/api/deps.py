"""Зависимости слоя API.

Здесь же строится контекст доступа. Это место выбрано намеренно: область
данных читается из базы, а слой безопасности не должен зависеть
от репозиториев. Композиционный корень доступен только API.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.business.analytics.service import AnalyticsService
from app.business.audit.service import AuditService
from app.business.forecasting.service import ForecastQueryService
from app.business.hospitals.service import HospitalService
from app.business.incidents.service import IncidentService
from app.business.ingestion.query import DataImportQueryService
from app.business.regions.service import RegionService
from app.business.signals.service import SignalService
from app.business.system.operations import OperationService
from app.composition import (
    build_analytics_service,
    build_audit_service,
    build_data_import_query_service,
    build_forecast_query_service,
    build_hospital_service,
    build_incident_service,
    build_region_service,
    build_signal_service,
    get_unit_of_work_factory,
)
from app.core.exceptions import UnauthenticatedError
from app.core.request_context import get_request_id
from app.security.authorization import AuthorizationService, get_authorization_service
from app.security.context import GLOBAL_SCOPE_ROLES, DataScope, SecurityContext
from app.security.oidc import get_token_verifier

# auto_error=False: собственный контракт ошибки вместо стандартного
# ответа FastAPI (API.md, раздел 1.2).
_bearer_scheme = HTTPBearer(auto_error=False, scheme_name="Keycloak OIDC")


def get_security_context(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
) -> SecurityContext:
    """Контекст доступа текущего пользователя.

    Роли приходят из токена, область данных — из базы MedSignal.
    Запасного пути аутентификации не существует: недоступность провайдера
    приводит к отказу, а не к пропуску проверки (ADR-0009).
    """
    if credentials is None or not credentials.credentials:
        raise UnauthenticatedError("Требуется токен доступа")

    claims = get_token_verifier().verify(credentials.credentials)

    with get_unit_of_work_factory()() as uow:
        # Проекция пользователя нужна внешним ключам авторства
        # и назначения. Прав она не выдаёт.
        user = uow.users.ensure(
            external_subject=claims.subject,
            display_name=claims.username,
            email=claims.email,
        )
        scope = uow.users.resolve_scope(user)
        internal_id = user.id
        uow.commit()

    # Глобальные роли получают полную область независимо от таблицы:
    # иначе первого администратора некому было бы настроить.
    if claims.roles & GLOBAL_SCOPE_ROLES:
        scope = DataScope.global_scope()

    context = SecurityContext(
        user_id=claims.subject,
        username=claims.username,
        email=claims.email,
        roles=claims.roles,
        scope=scope,
        token_id=claims.token_id,
        internal_user_id=internal_id,
    )
    # Идентификатор субъекта попадает в журнал; персональные данные — нет.
    request.state.user_id = context.user_id
    return context


CurrentUser = Annotated[SecurityContext, Depends(get_security_context)]


def get_current_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or get_request_id()


RequestIdDep = Annotated[str | None, Depends(get_current_request_id)]

# --- Бизнес-сервисы ---------------------------------------------------------

RegionServiceDep = Annotated[RegionService, Depends(build_region_service)]
HospitalServiceDep = Annotated[HospitalService, Depends(build_hospital_service)]
SignalServiceDep = Annotated[SignalService, Depends(build_signal_service)]
IncidentServiceDep = Annotated[IncidentService, Depends(build_incident_service)]
AuditServiceDep = Annotated[AuditService, Depends(build_audit_service)]
DataImportServiceDep = Annotated[
    DataImportQueryService, Depends(build_data_import_query_service)
]
AuthorizationDep = Annotated[AuthorizationService, Depends(get_authorization_service)]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(build_analytics_service)]
ForecastQueryServiceDep = Annotated[
    ForecastQueryService, Depends(build_forecast_query_service)
]


def get_operation_service() -> OperationService:
    """Служба технических операций PHASE 1.

    Оставлена без изменений: её использует служебный эндпоинт проверки
    фундамента.
    """
    return OperationService(get_unit_of_work_factory())


OperationServiceDep = Annotated[OperationService, Depends(get_operation_service)]
