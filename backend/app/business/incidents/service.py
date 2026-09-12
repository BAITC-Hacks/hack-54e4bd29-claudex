"""Правила работы с инцидентами.

Инцидент объединяет связанные сигналы одной ситуации. Автоматическая
кластеризация не выполняется: она требует накопленной статистики
совместных срабатываний и отложена (ADR-0008).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.business.ports import UnitOfWorkFactory
from app.core.exceptions import NotFoundError
from app.models.incident import Incident
from app.models.signal import Signal
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.permissions import Permission
from app.shared.filters import IncidentFilter
from app.shared.pagination import Page, PageRequest

INCIDENT_SORT_FIELDS: frozenset[str] = frozenset({"created_at", "status", "title"})
INCIDENT_DEFAULT_SORT = "created_at"


@dataclass(frozen=True, slots=True)
class IncidentDetail:
    incident: Incident
    signals: list[Signal]


class IncidentService:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, authorization: AuthorizationService
    ) -> None:
        self._uow_factory = uow_factory
        self._authz = authorization

    def list_incidents(
        self, context: SecurityContext, filters: IncidentFilter, page: PageRequest
    ) -> Page[Incident]:
        self._authz.require_permission(context, Permission.INCIDENT_READ)
        with self._uow_factory() as uow:
            items, total = uow.incidents.list(context.scope, filters, page)
        return Page.build(items, total, page)

    def get_incident(
        self, context: SecurityContext, incident_id: uuid.UUID
    ) -> IncidentDetail:
        self._authz.require_permission(context, Permission.INCIDENT_READ)
        with self._uow_factory() as uow:
            incident = uow.incidents.get(incident_id, context.scope)
            if incident is None:
                raise NotFoundError("Инцидент не найден")
            # Связанные сигналы тоже ограничены областью данных: инцидент
            # не должен становиться обходным путём к чужим сигналам.
            signals = uow.incidents.signals_of(incident_id, context.scope)
        return IncidentDetail(incident=incident, signals=signals)
