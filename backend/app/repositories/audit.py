"""Репозиторий журнала аудита.

Только добавление и чтение. Методов изменения и удаления нет намеренно:
смысл журнала в неизменности. Запрет на уровне прав СУБД вводится
отдельно и не заменяется дисциплиной кода.

Журнал ссылается на объекты разных типов, поэтому его видимость строится
по типу объекта: для сигналов и инцидентов проверяется организация,
для прочих типов запись доступна только обладателю глобальной области.
Правило намеренно строгое: журнал показывает, кто и чем занимался.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ColumnElement, and_, false, or_, select, true
from sqlalchemy.orm import Session

from app.models.analytics import Scenario
from app.models.audit import AuditEvent
from app.models.directory import Hospital
from app.models.enums import AuditAction, AuditEntityType
from app.models.incident import Incident
from app.models.signal import Signal
from app.repositories.directory import apply_sort, count_of
from app.repositories.scope import scoped_entity_clause
from app.security.context import DataScope
from app.shared.filters import AuditFilter
from app.shared.pagination import PageRequest

AUDIT_SORT_COLUMNS = {"created_at": AuditEvent.created_at}

type AuditPage = tuple[list[AuditEvent], int]
type AuditEventList = list[AuditEvent]


def audit_scope_clause(scope: DataScope) -> ColumnElement[bool]:
    """Условие видимости записи журнала."""
    if scope.is_global:
        return true()
    if not scope.resolved:
        return false()

    visible_signals = (
        select(Signal.id)
        .outerjoin(Hospital, Signal.hospital_id == Hospital.id)
        .where(
            scoped_entity_clause(
                scope,
                scope_type=Signal.scope_type,
                region_id=Signal.region_id,
                hospital_id=Signal.hospital_id,
            )
        )
    )
    visible_incidents = (
        select(Incident.id)
        .outerjoin(Hospital, Incident.hospital_id == Hospital.id)
        .where(
            scoped_entity_clause(
                scope,
                scope_type=Incident.scope_type,
                region_id=Incident.region_id,
                hospital_id=Incident.hospital_id,
            )
        )
    )
    visible_scenarios = (
        select(Scenario.id)
        .outerjoin(Hospital, Scenario.hospital_id == Hospital.id)
        .where(
            scoped_entity_clause(
                scope,
                scope_type=Scenario.scope_type,
                region_id=Scenario.region_id,
                hospital_id=Scenario.hospital_id,
            )
        )
    )

    return or_(
        and_(
            AuditEvent.entity_type == AuditEntityType.SIGNAL,
            AuditEvent.entity_id.in_(visible_signals),
        ),
        and_(
            AuditEvent.entity_type == AuditEntityType.INCIDENT,
            AuditEvent.entity_id.in_(visible_incidents),
        ),
        and_(
            AuditEvent.entity_type == AuditEntityType.SCENARIO,
            AuditEvent.entity_id.in_(visible_scenarios),
        ),
    )


class SqlAlchemyAuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        *,
        actor_user_id: uuid.UUID | None,
        action: AuditAction,
        entity_type: AuditEntityType,
        entity_id: uuid.UUID,
        request_id: str | None,
        metadata: dict[str, Any],
    ) -> AuditEvent:
        event = AuditEvent(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id,
            event_metadata=metadata,
        )
        self._session.add(event)
        self._session.flush()
        return event

    def list(
        self, scope: DataScope, filters: AuditFilter, page: PageRequest
    ) -> AuditPage:
        statement = select(AuditEvent).where(audit_scope_clause(scope))

        if filters.entity_type is not None:
            statement = statement.where(AuditEvent.entity_type == filters.entity_type)
        if filters.entity_id is not None:
            statement = statement.where(AuditEvent.entity_id == filters.entity_id)
        if filters.actor_user_id is not None:
            statement = statement.where(AuditEvent.actor_user_id == filters.actor_user_id)
        if filters.action is not None:
            statement = statement.where(AuditEvent.action == filters.action)
        if filters.date_from is not None:
            statement = statement.where(AuditEvent.created_at >= filters.date_from)
        if filters.date_to is not None:
            statement = statement.where(AuditEvent.created_at <= filters.date_to)

        total = count_of(self._session, statement)
        statement = apply_sort(statement, page, AUDIT_SORT_COLUMNS)
        rows = self._session.scalars(
            statement.offset(page.offset).limit(page.limit)
        ).all()
        return list(rows), total

    def list_for_entity(
        self, entity_type: AuditEntityType, entity_id: uuid.UUID, *, limit: int
    ) -> AuditEventList:
        statement = (
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        return list(self._session.scalars(statement).all())
