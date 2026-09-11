"""Схемы служебных эндпоинтов: здоровье, готовность, операции, контекст доступа."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.system import OperationStatus


class HealthResponse(BaseModel):
    """Ответ liveness. Зависимости не проверяются."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str


class DependencyStatus(BaseModel):
    """Состояние одной зависимости."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["up", "down", "skipped"]
    required: bool
    latency_ms: float | None = None
    # Краткая причина отказа без внутренних деталей: адреса, имена баз
    # и трассировки наружу не уходят.
    reason: str | None = None


class ReadinessResponse(BaseModel):
    """Ответ readiness.

    Код 200 означает, что все обязательные зависимости доступны.
    Необязательные попадают в отчёт, но не влияют на код ответа.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "not_ready"]
    service: str
    version: str
    dependencies: list[DependencyStatus]


class OperationResponse(BaseModel):
    """Состояние долгой операции (ADR-0010)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    operation_type: str
    status: OperationStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_summary: str | None = None
    result: dict[str, Any] | None = None


class OperationAccepted(BaseModel):
    """Ответ на постановку операции в очередь."""

    model_config = ConfigDict(extra="forbid")

    operation_id: uuid.UUID
    status: OperationStatus
    message: str = "Операция принята в обработку"


class SecurityContextResponse(BaseModel):
    """Контекст доступа текущего пользователя.

    Защищённый служебный эндпоинт PHASE 1: показывает, что токен Keycloak
    разобран корректно. Полноценная доменная авторизация — PHASE 2.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str
    username: str | None = None
    roles: list[str]
    region_ids: list[str] = Field(default_factory=list)
    hospital_ids: list[str] = Field(default_factory=list)
    has_global_scope: bool = False
    scope_resolved: bool = Field(
        description="Разрешена ли область данных. В PHASE 1 всегда false: "
        "таблица областей появляется в PHASE 2"
    )
