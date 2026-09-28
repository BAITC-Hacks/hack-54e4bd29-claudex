"""Схемы ответов о загрузке данных.

Ни одна схема здесь не содержит значений из выгрузок. Наружу выходят
счётчики, коды правил и текст замечаний — то, по чему видно состояние
поставки, но не то, что в ней лежало.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DataImportStatus, DatasetType, QualitySeverity

_RESPONSE = ConfigDict(extra="forbid", from_attributes=True)


class DataImportListItem(BaseModel):
    model_config = _RESPONSE

    id: uuid.UUID
    dataset_type: str
    source: str
    file_name: str
    file_hash: str = Field(description="SHA-256 содержимого исходного файла")
    status: DataImportStatus
    rows_read: int
    rows_loaded: int
    rows_rejected: int
    created_at: datetime
    completed_at: datetime | None


class DataImportResponse(DataImportListItem):
    model_config = _RESPONSE

    rows_valid: int
    warnings_count: int
    source_size_bytes: int
    duration_seconds: float
    started_at: datetime | None
    error_summary: str | None
    request_id: str | None


class DataQualityFindingResponse(BaseModel):
    model_config = _RESPONSE

    validation_level: str
    rule_code: str
    severity: QualitySeverity
    column_name: str | None
    affected_rows: int
    message: str = Field(
        description="Формулировка со счётчиками. Значений из выгрузки не содержит"
    )


class DataQualityReportResponse(BaseModel):
    model_config = _RESPONSE

    data_import_id: uuid.UUID
    dataset_type: str
    status: DataImportStatus
    rows_read: int
    rows_valid: int
    rows_rejected: int
    rows_loaded: int
    warnings_count: int
    findings: list[DataQualityFindingResponse]


class DatasetTypeFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_type: DatasetType | None = None
