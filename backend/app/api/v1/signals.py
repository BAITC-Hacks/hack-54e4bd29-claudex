"""Маршруты сигналов и инцидентов."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, IncidentServiceDep, SignalServiceDep
from app.api.v1.mappers import (
    incident_list_item,
    incident_response,
    page_meta,
    signal_list_item,
    signal_response,
)
from app.business.incidents.service import (
    INCIDENT_DEFAULT_SORT,
    INCIDENT_SORT_FIELDS,
)
from app.business.signals.service import SIGNAL_DEFAULT_SORT, SIGNAL_SORT_FIELDS
from app.models.enums import (
    IncidentStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
)
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.domain import (
    IncidentListItem,
    IncidentResponse,
    SignalAssignRequest,
    SignalListItem,
    SignalResponse,
    SignalStatusUpdateRequest,
    SignalUnassignRequest,
)
from app.shared.filters import IncidentFilter, SignalFilter
from app.shared.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    build_page_request,
)

router = APIRouter(tags=["signals"], responses=ERROR_RESPONSES)

PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]


@router.get(
    "/signals",
    response_model=Page[SignalListItem],
    summary="Лента предупреждений",
    description=(
        "Фильтры типизированы, сортировка ограничена списком разрешённых "
        "полей. Выдача всегда постраничная."
    ),
)
def list_signals(
    context: CurrentUser,
    service: SignalServiceDep,
    hospital_id: uuid.UUID | None = None,
    region_id: uuid.UUID | None = None,
    signal_status: Annotated[SignalStatus | None, Query(alias="status")] = None,
    severity: SignalSeverity | None = None,
    signal_type: Annotated[SignalType | None, Query(alias="type")] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    assigned_user_id: uuid.UUID | None = None,
    page: PageNumber = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    sort_by: str | None = None,
    sort_desc: bool = True,
) -> Page[SignalListItem]:
    request = build_page_request(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_desc=sort_desc,
        allowed_sort_fields=SIGNAL_SORT_FIELDS,
        default_sort_field=SIGNAL_DEFAULT_SORT,
    )
    filters = SignalFilter(
        hospital_id=hospital_id,
        region_id=region_id,
        status=signal_status,
        severity=severity,
        signal_type=signal_type,
        date_from=date_from,
        date_to=date_to,
        assigned_user_id=assigned_user_id,
    )
    result = service.list_signals(context, filters, request)
    return Page[SignalListItem](
        items=[signal_list_item(item) for item in result.items], **page_meta(result)
    )


@router.get(
    "/signals/{signal_id}",
    response_model=SignalResponse,
    summary="Карточка сигнала",
    description=(
        "Перечень доступных переходов вычисляет сервер с учётом роли. "
        "Сигнал вне области данных возвращает 404."
    ),
)
def get_signal(
    signal_id: uuid.UUID, context: CurrentUser, service: SignalServiceDep
) -> SignalResponse:
    return signal_response(service.get_signal(context, signal_id))


@router.patch(
    "/signals/{signal_id}/status",
    response_model=SignalResponse,
    summary="Смена статуса сигнала",
    description=(
        "Переход проверяется конечным автоматом. Поле `version` обязательно: "
        "расхождение версии означает, что карточку изменил другой "
        "сотрудник, и возвращается 409."
    ),
    responses={409: {"description": "Сигнал изменён другим пользователем"}},
)
def update_signal_status(
    signal_id: uuid.UUID,
    payload: SignalStatusUpdateRequest,
    context: CurrentUser,
    service: SignalServiceDep,
) -> SignalResponse:
    detail = service.change_status(
        context,
        signal_id,
        target_status=payload.status,
        expected_version=payload.version,
        reason=payload.reason,
    )
    return signal_response(detail)


@router.post(
    "/signals/{signal_id}/assign",
    response_model=SignalResponse,
    status_code=status.HTTP_200_OK,
    summary="Назначить ответственного",
    description=(
        "Ответственный обязан иметь доступ к организации сигнала: иначе "
        "создаётся задача, которую невозможно выполнить."
    ),
)
def assign_signal(
    signal_id: uuid.UUID,
    payload: SignalAssignRequest,
    context: CurrentUser,
    service: SignalServiceDep,
) -> SignalResponse:
    detail = service.assign(
        context,
        signal_id,
        assignee_id=payload.assignee_id,
        expected_version=payload.version,
    )
    return signal_response(detail)


@router.delete(
    "/signals/{signal_id}/assign",
    response_model=SignalResponse,
    summary="Снять ответственного",
)
def unassign_signal(
    signal_id: uuid.UUID,
    payload: SignalUnassignRequest,
    context: CurrentUser,
    service: SignalServiceDep,
) -> SignalResponse:
    detail = service.unassign(context, signal_id, expected_version=payload.version)
    return signal_response(detail)


@router.get(
    "/incidents",
    response_model=Page[IncidentListItem],
    summary="Список инцидентов",
)
def list_incidents(
    context: CurrentUser,
    service: IncidentServiceDep,
    hospital_id: uuid.UUID | None = None,
    region_id: uuid.UUID | None = None,
    incident_status: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    page: PageNumber = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    sort_by: str | None = None,
    sort_desc: bool = True,
) -> Page[IncidentListItem]:
    request = build_page_request(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_desc=sort_desc,
        allowed_sort_fields=INCIDENT_SORT_FIELDS,
        default_sort_field=INCIDENT_DEFAULT_SORT,
    )
    filters = IncidentFilter(
        hospital_id=hospital_id, region_id=region_id, status=incident_status
    )
    result = service.list_incidents(context, filters, request)
    return Page[IncidentListItem](
        items=[incident_list_item(item) for item in result.items], **page_meta(result)
    )


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
    summary="Инцидент со связанными сигналами",
)
def get_incident(
    incident_id: uuid.UUID, context: CurrentUser, service: IncidentServiceDep
) -> IncidentResponse:
    return incident_response(service.get_incident(context, incident_id))
