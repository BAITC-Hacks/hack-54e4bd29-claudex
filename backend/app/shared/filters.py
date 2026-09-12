"""Проверенные фильтры выборки.

Фильтр — это набор типизированных полей, а не строка с условием.
Произвольные выражения извне в запрос не попадают.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.core.exceptions import ValidationError
from app.models.enums import (
    IncidentStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
)


@dataclass(frozen=True, slots=True)
class SignalFilter:
    """Фильтры ленты предупреждений."""

    hospital_id: uuid.UUID | None = None
    region_id: uuid.UUID | None = None
    status: SignalStatus | None = None
    severity: SignalSeverity | None = None
    signal_type: SignalType | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    assigned_user_id: uuid.UUID | None = None

    def validate(self) -> None:
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValidationError(
                "Начало периода не может быть позже его конца",
                details={
                    "date_from": self.date_from.isoformat(),
                    "date_to": self.date_to.isoformat(),
                },
            )


@dataclass(frozen=True, slots=True)
class HospitalFilter:
    region_id: uuid.UUID | None = None
    is_active: bool | None = None


@dataclass(frozen=True, slots=True)
class IncidentFilter:
    hospital_id: uuid.UUID | None = None
    region_id: uuid.UUID | None = None
    status: IncidentStatus | None = None


@dataclass(frozen=True, slots=True)
class AuditFilter:
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    action: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
