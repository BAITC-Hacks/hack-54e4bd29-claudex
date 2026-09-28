"""Human-controlled Incident workflow built on existing scoped domain objects."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.business.ports import UnitOfWorkFactory
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.request_context import get_request_id
from app.models.action import Action
from app.models.enums import (
    ActionType,
    AuditAction,
    AuditEntityType,
    DataScopeType,
    IncidentStatus,
)
from app.models.incident import Incident
from app.models.signal import Signal
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, SecurityContext
from app.security.permissions import Permission
from app.shared.filters import IncidentFilter
from app.shared.pagination import Page, PageRequest

INCIDENT_SORT_FIELDS: frozenset[str] = frozenset({"created_at", "status", "title"})
INCIDENT_DEFAULT_SORT = "created_at"


@dataclass(frozen=True, slots=True)
class IncidentDetail:
    incident: Incident
    signals: list[Signal]
    actions: list[Action]


def _now() -> datetime:
    return datetime.now(tz=UTC)


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
            signals = uow.incidents.signals_of(incident_id, context.scope)
            actions = uow.actions.list_for_incident(incident_id)
        return IncidentDetail(incident=incident, signals=signals, actions=actions)

    def create_from_signal(
        self,
        context: SecurityContext,
        signal_id: uuid.UUID,
        *,
        expected_signal_version: int,
        title: str,
        description: str | None,
    ) -> IncidentDetail:
        self._authz.require_permission(context, Permission.INCIDENT_MANAGE)
        normalized_title = title.strip()
        if not normalized_title:
            raise ValidationError("Название инцидента обязательно")
        normalized_description = description.strip() if description else None

        with self._uow_factory() as uow:
            signal = uow.signals.get(signal_id, context.scope)
            if signal is None:
                raise NotFoundError("Сигнал не найден")
            if signal.incident_id is not None:
                existing_id = signal.incident_id
            else:
                now = _now()
                incident = Incident(
                    id=uuid.uuid4(),
                    scope_type=signal.scope_type,
                    region_id=signal.region_id,
                    hospital_id=signal.hospital_id,
                    title=normalized_title,
                    description=normalized_description,
                    status=IncidentStatus.OPEN,
                    assigned_user_id=None,
                    created_by=context.actor_id,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                uow.incidents.add(incident)
                linked = uow.signals.link_incident(
                    signal_id,
                    expected_version=expected_signal_version,
                    incident_id=incident.id,
                    now=now,
                )
                if linked is None:
                    raise ConflictError(
                        "Сигнал был изменён другим пользователем. Обновите карточку",
                        details={"expected_version": expected_signal_version},
                    )
                uow.actions.add(
                    Action(
                        signal_id=signal_id,
                        incident_id=incident.id,
                        created_by=context.actor_id,
                        action_type=ActionType.DECISION_RECORDED,
                        description="Создан инцидент из сигнала",
                    )
                )
                uow.audit.append(
                    actor_user_id=context.actor_id,
                    action=AuditAction.INCIDENT_CREATED_FROM_SIGNAL,
                    entity_type=AuditEntityType.INCIDENT,
                    entity_id=incident.id,
                    request_id=get_request_id(),
                    metadata={"signal_id": str(signal_id)},
                )
                uow.commit()
                existing_id = incident.id
        return self.get_incident(context, existing_id)

    def assign(
        self,
        context: SecurityContext,
        incident_id: uuid.UUID,
        *,
        assignee_id: uuid.UUID,
        expected_version: int,
    ) -> IncidentDetail:
        self._authz.require_permission(context, Permission.INCIDENT_MANAGE)
        with self._uow_factory() as uow:
            incident = uow.incidents.get(incident_id, context.scope)
            if incident is None:
                raise NotFoundError("Инцидент не найден")
            assignee = uow.users.get(assignee_id)
            if assignee is None or not assignee.is_active:
                raise ValidationError("Указанный пользователь недоступен для назначения")
            assignee_scope = (
                context.scope
                if assignee.id == context.actor_id
                else uow.users.resolve_scope(assignee)
            )
            if not self._scope_covers_incident(assignee_scope, incident):
                raise ValidationError(
                    "Ответственный не имеет доступа к области инцидента"
                )
            updated = uow.incidents.update_assignment(
                incident_id,
                expected_version=expected_version,
                assigned_user_id=assignee_id,
                now=_now(),
            )
            if updated is None:
                raise ConflictError(
                    "Инцидент был изменён другим пользователем. Обновите карточку",
                    details={"expected_version": expected_version},
                )
            uow.actions.add(
                Action(
                    incident_id=incident_id,
                    created_by=context.actor_id,
                    action_type=ActionType.ASSIGNMENT,
                    description="Назначен ответственный за инцидент",
                )
            )
            uow.audit.append(
                actor_user_id=context.actor_id,
                action=AuditAction.INCIDENT_ASSIGNED,
                entity_type=AuditEntityType.INCIDENT,
                entity_id=incident_id,
                request_id=get_request_id(),
                metadata={"assignee_id": str(assignee_id)},
            )
            uow.commit()
        return self.get_incident(context, incident_id)

    def change_status(
        self,
        context: SecurityContext,
        incident_id: uuid.UUID,
        *,
        target_status: IncidentStatus,
        expected_version: int,
        reason: str,
    ) -> IncidentDetail:
        self._authz.require_permission(context, Permission.INCIDENT_MANAGE)
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValidationError("Причина изменения статуса обязательна")
        with self._uow_factory() as uow:
            incident = uow.incidents.get(incident_id, context.scope)
            if incident is None:
                raise NotFoundError("Инцидент не найден")
            current = IncidentStatus(incident.status)
            if current is target_status:
                raise ValidationError("Инцидент уже находится в указанном статусе")
            updated = uow.incidents.update_status(
                incident_id,
                expected_version=expected_version,
                status=target_status,
                now=_now(),
            )
            if updated is None:
                raise ConflictError(
                    "Инцидент был изменён другим пользователем. Обновите карточку",
                    details={"expected_version": expected_version},
                )
            uow.actions.add(
                Action(
                    incident_id=incident_id,
                    created_by=context.actor_id,
                    action_type=ActionType.STATUS_CHANGE,
                    description=normalized_reason,
                )
            )
            uow.audit.append(
                actor_user_id=context.actor_id,
                action=AuditAction.INCIDENT_STATUS_CHANGED,
                entity_type=AuditEntityType.INCIDENT,
                entity_id=incident_id,
                request_id=get_request_id(),
                metadata={
                    "from": current.value,
                    "to": target_status.value,
                    "reason": normalized_reason,
                },
            )
            uow.commit()
        return self.get_incident(context, incident_id)

    @staticmethod
    def _scope_covers_incident(scope: DataScope, incident: Incident) -> bool:
        if scope.is_global:
            return True
        if not scope.resolved:
            return False
        scope_type = DataScopeType(incident.scope_type)
        if scope_type is DataScopeType.GLOBAL:
            return False
        if scope_type is DataScopeType.REGION:
            return (
                incident.region_id is not None
                and str(incident.region_id) in scope.region_ids
            )
        if incident.hospital_id is None:
            return False
        if str(incident.hospital_id) in scope.hospital_ids:
            return True
        hospital = getattr(incident, "hospital", None)
        region_id = getattr(hospital, "region_id", None)
        return region_id is not None and str(region_id) in scope.region_ids
