"""Маршруты справочников: регионы и медицинские организации.

Маршрут отвечает за разбор запроса, вызов сервиса и сериализацию.
Правил доступа и фильтрации по области данных здесь нет: они
в бизнес-слое и в репозиториях.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, HospitalServiceDep, RegionServiceDep
from app.api.v1.mappers import (
    hospital_list_item,
    hospital_response,
    page_meta,
    region_list_item,
    region_response,
)
from app.business.hospitals.service import HOSPITAL_DEFAULT_SORT, HOSPITAL_SORT_FIELDS
from app.business.regions.service import REGION_DEFAULT_SORT, REGION_SORT_FIELDS
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.domain import (
    HospitalListItem,
    HospitalResponse,
    RegionListItem,
    RegionResponse,
)
from app.shared.filters import HospitalFilter
from app.shared.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    build_page_request,
)

router = APIRouter(tags=["directory"], responses=ERROR_RESPONSES)

PageNumber = Annotated[int, Query(ge=1, description="Номер страницы")]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Размер страницы")]


@router.get(
    "/regions",
    response_model=Page[RegionListItem],
    summary="Список регионов",
    description="Возвращает только регионы из области данных пользователя.",
)
def list_regions(
    context: CurrentUser,
    service: RegionServiceDep,
    page: PageNumber = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    sort_by: str | None = None,
    sort_desc: bool = False,
) -> Page[RegionListItem]:
    request = build_page_request(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_desc=sort_desc,
        allowed_sort_fields=REGION_SORT_FIELDS,
        default_sort_field=REGION_DEFAULT_SORT,
    )
    result = service.list_regions(context, request)
    return Page[RegionListItem](
        items=[region_list_item(item) for item in result.items], **page_meta(result)
    )


@router.get(
    "/regions/{region_id}",
    response_model=RegionResponse,
    summary="Регион",
    description=(
        "Регион вне области данных пользователя возвращает 404: различие "
        "ответов раскрывало бы существование объекта."
    ),
)
def get_region(
    region_id: uuid.UUID, context: CurrentUser, service: RegionServiceDep
) -> RegionResponse:
    return region_response(service.get_region(context, region_id))


@router.get(
    "/hospitals",
    response_model=Page[HospitalListItem],
    summary="Список медицинских организаций",
)
def list_hospitals(
    context: CurrentUser,
    service: HospitalServiceDep,
    region_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    page: PageNumber = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    sort_by: str | None = None,
    sort_desc: bool = False,
) -> Page[HospitalListItem]:
    request = build_page_request(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_desc=sort_desc,
        allowed_sort_fields=HOSPITAL_SORT_FIELDS,
        default_sort_field=HOSPITAL_DEFAULT_SORT,
    )
    result = service.list_hospitals(
        context, HospitalFilter(region_id=region_id, is_active=is_active), request
    )
    return Page[HospitalListItem](
        items=[hospital_list_item(item) for item in result.items], **page_meta(result)
    )


@router.get(
    "/hospitals/{hospital_id}",
    response_model=HospitalResponse,
    summary="Медицинская организация",
    description=(
        "Организация вне области данных пользователя возвращает 404. "
        "Это основная защита от перебора идентификаторов."
    ),
)
def get_hospital(
    hospital_id: uuid.UUID, context: CurrentUser, service: HospitalServiceDep
) -> HospitalResponse:
    return hospital_response(service.get_hospital(context, hospital_id))
