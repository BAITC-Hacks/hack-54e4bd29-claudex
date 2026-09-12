"""Контракты API предметной области.

Схемы ответа описаны явно и не строятся из моделей SQLAlchemy: модель
содержит поля, которых клиенту знать не нужно, и любое её расширение
иначе немедленно утекало бы наружу.

Схемы запроса запрещают лишние поля. Это защита от массового присвоения:
клиент не должен иметь возможности прислать `version` или `status`
там, где их изменение не предусмотрено операцией.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ActionType,
    AuditAction,
    AuditEntityType,
    IncidentStatus,
    SignalSeverity,
    SignalSourceType,
    SignalStatus,
    SignalType,
)

# protected_namespaces=(): поле `model_version` — часть предметной
# области (версия ML-модели), а не служебное имя pydantic.
_RESPONSE = ConfigDict(extra="forbid", from_attributes=True, protected_namespaces=())
_REQUEST = ConfigDict(extra="forbid")


# --- Регионы ----------------------------------------------------------------


class RegionListItem(BaseModel):
    model_config = _RESPONSE

    id: uuid.UUID
    code: str
    name: str
    is_active: bool


class RegionResponse(RegionListItem):
    model_config = _RESPONSE

    created_at: datetime
    updated_at: datetime


# --- Медицинские организации ------------------------------------------------


class HospitalListItem(BaseModel):
    model_config = _RESPONSE

    id: uuid.UUID
    code: str
    name: str
    region_id: uuid.UUID
    is_active: bool


class HospitalResponse(HospitalListItem):
    model_config = _RESPONSE

    region_name: str | None = None
    created_at: datetime
    updated_at: datetime


# --- Сигналы ----------------------------------------------------------------


class SignalListItem(BaseModel):
    """Строка ленты предупреждений."""

    model_config = _RESPONSE

    id: uuid.UUID
    hospital_id: uuid.UUID
    hospital_name: str | None = None
    type: SignalType
    severity: SignalSeverity
    status: SignalStatus
    source_type: SignalSourceType
    title: str
    detected_at: datetime
    assigned_user_id: uuid.UUID | None = None
    version: int


class ExplanationFactor(BaseModel):
    """Один фактор объяснения в структурированном виде."""

    model_config = _RESPONSE

    metric_code: str
    direction: str
    change_pct: float | None = None
    comparison_period: str | None = None


class SignalExplanationResponse(BaseModel):
    """Объяснение вместе со сведениями о происхождении.

    Происхождение обязательно: утверждение без источника невозможно
    перепроверить (BUSINESS_LOGIC.md, раздел 5).
    """

    model_config = _RESPONSE

    summary: str
    factors: list[ExplanationFactor]
    caveats: list[str]
    generator: str
    generator_version: str
    model_version: str | None = None
    input_period_start: datetime | None = None
    input_period_end: datetime | None = None
    generated_at: datetime


class ActionResponse(BaseModel):
    """Действие человека."""

    model_config = _RESPONSE

    id: uuid.UUID
    action_type: ActionType
    description: str
    created_by: uuid.UUID
    created_at: datetime


class AuditEventResponse(BaseModel):
    model_config = _RESPONSE

    id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    action: AuditAction
    entity_type: AuditEntityType
    entity_id: uuid.UUID
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SignalResponse(BaseModel):
    """Карточка сигнала."""

    model_config = _RESPONSE

    id: uuid.UUID
    hospital_id: uuid.UUID
    hospital_name: str | None = None
    region_id: uuid.UUID | None = None
    type: SignalType
    severity: SignalSeverity
    status: SignalStatus
    source_type: SignalSourceType
    title: str
    summary: str
    detected_at: datetime
    created_at: datetime
    updated_at: datetime
    forecast_id: uuid.UUID | None = None
    incident_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None
    closed_reason: str | None = None
    closed_at: datetime | None = None
    version: int

    # Перечень переходов вычисляет сервер с учётом роли: решать это
    # на стороне клиента нельзя (BUSINESS_LOGIC.md, раздел 4.5).
    available_transitions: list[SignalStatus]
    explanation: SignalExplanationResponse | None = None
    actions: list[ActionResponse] = Field(default_factory=list)
    audit_history: list[AuditEventResponse] = Field(default_factory=list)


class SignalStatusUpdateRequest(BaseModel):
    """Смена статуса сигнала.

    `version` обязателен: без него невозможно обнаружить, что карточку
    уже изменил другой сотрудник.
    """

    model_config = _REQUEST

    status: SignalStatus
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)


class SignalAssignRequest(BaseModel):
    model_config = _REQUEST

    assignee_id: uuid.UUID
    version: int = Field(ge=1)


class SignalUnassignRequest(BaseModel):
    model_config = _REQUEST

    version: int = Field(ge=1)


# --- Инциденты --------------------------------------------------------------


class IncidentListItem(BaseModel):
    model_config = _RESPONSE

    id: uuid.UUID
    hospital_id: uuid.UUID
    title: str
    status: IncidentStatus
    created_at: datetime


class IncidentResponse(IncidentListItem):
    model_config = _RESPONSE

    description: str | None = None
    updated_at: datetime
    signals: list[SignalListItem] = Field(default_factory=list)
