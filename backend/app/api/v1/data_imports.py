"""Маршруты истории загрузок.

Только чтение. Запуск импорта через HTTP не предусмотрен: загрузка читает
файлы с диска сервера, и приём пути в теле запроса означал бы чтение
произвольного файла от имени приложения. Импорт запускается командой
`python -m app.cli.data import`, а будущий приём файлов от пользователя
будет работать через объектное хранилище, а не через путь в запросе.

Доступ ограничен правом на чтение импортов. Оно есть у администратора
и у уполномоченного органа; ролям организации и региональному аналитику
оно не выдано: состав поставок относится к работе системы, а не
к наблюдению за ситуацией.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DataImportServiceDep
from app.api.v1.mappers import page_meta
from app.models.enums import DatasetType
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.data_import import (
    DataImportListItem,
    DataImportResponse,
    DataQualityFindingResponse,
    DataQualityReportResponse,
)
from app.shared.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    build_page_request,
)

router = APIRouter(tags=["data-imports"], responses=ERROR_RESPONSES)

# Сортировка одна: новые сверху. Импорты просматривают, чтобы увидеть
# последнюю поставку, и произвольная сортировка здесь не нужна.
IMPORT_SORT_FIELDS = frozenset({"created_at"})
IMPORT_DEFAULT_SORT = "created_at"


@router.get(
    "/data-imports",
    response_model=Page[DataImportListItem],
    summary="История загрузок",
)
def list_data_imports(
    context: CurrentUser,
    service: DataImportServiceDep,
    dataset_type: DatasetType | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Page[DataImportListItem]:
    request = build_page_request(
        page=page,
        page_size=page_size,
        sort_by=IMPORT_DEFAULT_SORT,
        sort_desc=True,
        allowed_sort_fields=IMPORT_SORT_FIELDS,
        default_sort_field=IMPORT_DEFAULT_SORT,
    )
    result = service.list_imports(context, request, dataset_type)
    return Page(
        items=[DataImportListItem.model_validate(item) for item in result.items],
        **page_meta(result),
    )


@router.get(
    "/data-imports/{import_id}",
    response_model=DataImportResponse,
    summary="Одна загрузка",
)
def get_data_import(
    import_id: uuid.UUID,
    context: CurrentUser,
    service: DataImportServiceDep,
) -> DataImportResponse:
    return DataImportResponse.model_validate(service.get_import(context, import_id))


@router.get(
    "/data-imports/{import_id}/quality",
    response_model=DataQualityReportResponse,
    summary="Отчёт о качестве загрузки",
    description=(
        "Замечания в агрегированном виде: правило, столбец и число "
        "затронутых строк. Значений из выгрузки отчёт не содержит."
    ),
)
def get_data_import_quality(
    import_id: uuid.UUID,
    context: CurrentUser,
    service: DataImportServiceDep,
) -> DataQualityReportResponse:
    data_import = service.get_import(context, import_id)
    findings = service.get_quality(context, import_id)
    return DataQualityReportResponse(
        data_import_id=data_import.id,
        dataset_type=data_import.dataset_type,
        status=data_import.status,
        rows_read=data_import.rows_read,
        rows_valid=data_import.rows_valid,
        rows_rejected=data_import.rows_rejected,
        rows_loaded=data_import.rows_loaded,
        warnings_count=data_import.warnings_count,
        findings=[
            DataQualityFindingResponse.model_validate(finding) for finding in findings
        ],
    )
