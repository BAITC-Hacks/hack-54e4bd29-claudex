"""Маршрут журнала аудита.

Журнал сам является чувствительным объектом: он показывает, кто и чем
занимался. Поэтому чтение требует отдельного права и ограничено
областью данных пользователя.

Методов изменения и удаления нет намеренно: журнал только пополняется.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AuditServiceDep, CurrentUser
from app.api.v1.mappers import audit_event_response, page_meta
from app.business.audit.service import AUDIT_DEFAULT_SORT, AUDIT_SORT_FIELDS
from app.models.enums import AuditAction, AuditEntityType
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.domain import AuditEventResponse
from app.shared.filters import AuditFilter
from app.shared.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    build_page_request,
)

router = APIRouter(tags=["audit"], responses=ERROR_RESPONSES)


@router.get(
    "/audit",
    response_model=Page[AuditEventResponse],
    summary="Журнал аудита",
    description=(
        "Возвращает записи об объектах из области данных пользователя. "
        "Записи о недоступных объектах не показываются."
    ),
)
def list_audit_events(
    context: CurrentUser,
    service: AuditServiceDep,
    entity_type: AuditEntityType | None = None,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: AuditAction | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    sort_desc: bool = True,
) -> Page[AuditEventResponse]:
    request = build_page_request(
        page=page,
        page_size=page_size,
        sort_by=AUDIT_DEFAULT_SORT,
        sort_desc=sort_desc,
        allowed_sort_fields=AUDIT_SORT_FIELDS,
        default_sort_field=AUDIT_DEFAULT_SORT,
    )
    filters = AuditFilter(
        entity_type=entity_type.value if entity_type else None,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        action=action.value if action else None,
        date_from=date_from,
        date_to=date_to,
    )
    result = service.list_events(context, filters, request)
    return Page[AuditEventResponse](
        items=[audit_event_response(item) for item in result.items],
        **page_meta(result),
    )
