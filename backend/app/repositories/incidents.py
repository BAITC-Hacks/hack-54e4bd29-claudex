"""Репозитории инцидентов и действий."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, contains_eager

from app.models.action import Action
from app.models.directory import Hospital
from app.models.incident import Incident
from app.models.signal import Signal
from app.repositories.directory import apply_sort, count_of
from app.repositories.scope import hospital_clause
from app.security.context import DataScope
from app.shared.filters import IncidentFilter
from app.shared.pagination import PageRequest

type IncidentPage = tuple[list[Incident], int]
type SignalList = list[Signal]

INCIDENT_SORT_COLUMNS = {
    "created_at": Incident.created_at,
    "status": Incident.status,
    "title": Incident.title,
}


class SqlAlchemyIncidentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _scoped(self, scope: DataScope) -> Select[tuple[Incident]]:
        return (
            select(Incident)
            .join(Hospital, Incident.hospital_id == Hospital.id)
            .where(hospital_clause(scope))
        )

    def get(self, incident_id: uuid.UUID, scope: DataScope) -> Incident | None:
        statement = self._scoped(scope).where(Incident.id == incident_id)
        return self._session.scalars(statement).unique().first()

    def list(
        self, scope: DataScope, filters: IncidentFilter, page: PageRequest
    ) -> IncidentPage:
        statement = self._scoped(scope)
        if filters.hospital_id is not None:
            statement = statement.where(Incident.hospital_id == filters.hospital_id)
        if filters.region_id is not None:
            statement = statement.where(Hospital.region_id == filters.region_id)
        if filters.status is not None:
            statement = statement.where(Incident.status == filters.status)

        total = count_of(self._session, statement)
        statement = apply_sort(statement, page, INCIDENT_SORT_COLUMNS)
        rows = (
            self._session.scalars(statement.offset(page.offset).limit(page.limit))
            .unique()
            .all()
        )
        return list(rows), total

    def signals_of(self, incident_id: uuid.UUID, scope: DataScope) -> SignalList:
        """Сигналы инцидента, ограниченные областью данных.

        Ограничение повторяется намеренно: инцидент не должен становиться
        обходным путём к сигналам чужих организаций.
        """
        statement = (
            select(Signal)
            .join(Hospital, Signal.hospital_id == Hospital.id)
            .options(contains_eager(Signal.hospital))
            .where(Signal.incident_id == incident_id, hospital_clause(scope))
            .order_by(Signal.detected_at.desc())
        )
        return list(self._session.scalars(statement).unique().all())


class SqlAlchemyActionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, action: Action) -> Action:
        self._session.add(action)
        self._session.flush()
        return action

    def list_for_signal(self, signal_id: uuid.UUID) -> list[Action]:
        statement = (
            select(Action)
            .where(Action.signal_id == signal_id)
            .order_by(Action.created_at.desc())
            .limit(100)
        )
        return list(self._session.scalars(statement).all())
