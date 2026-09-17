"""Репозиторий сигналов.

Содержит два нетривиальных места:

* область данных требует соединения с организациями, потому что сигнал
  может быть виден и через регион, и через конкретную организацию;
* смена статуса и назначение выполняются условным обновлением по версии.
  Это и есть защита от потерянного обновления: два сотрудника,
  открывшие карточку одновременно, не затрут решение друг друга молча.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from app.models.directory import Hospital
from app.models.enums import SignalClosureDisposition, SignalStatus
from app.models.signal import Signal
from app.repositories.directory import apply_sort, count_of
from app.repositories.scope import scoped_entity_clause
from app.security.context import DataScope
from app.shared.filters import SignalFilter
from app.shared.pagination import PageRequest

# Псевдоним нужен потому, что внутри класса имя `list` занято методом:
# аннотация `list[Signal]` разрешилась бы в него, а не во встроенный тип.
type SignalPage = tuple[list[Signal], int]

SIGNAL_SORT_COLUMNS = {
    "detected_at": Signal.detected_at,
    "created_at": Signal.created_at,
    "severity": Signal.severity,
    "status": Signal.status,
    "type": Signal.type,
}


class SqlAlchemySignalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Чтение
    # ------------------------------------------------------------------

    def _scoped(self, scope: DataScope) -> Select[tuple[Signal]]:
        """Базовая выборка сигналов, ограниченная областью данных.

        Соединение с организациями обязательно: без него условие области
        по региону выразить нельзя.
        """
        return (
            select(Signal)
            .outerjoin(Hospital, Signal.hospital_id == Hospital.id)
            .options(contains_eager(Signal.hospital))
            .where(
                scoped_entity_clause(
                    scope,
                    scope_type=Signal.scope_type,
                    region_id=Signal.region_id,
                    hospital_id=Signal.hospital_id,
                )
            )
        )

    def get(self, signal_id: uuid.UUID, scope: DataScope) -> Signal | None:
        statement = self._scoped(scope).where(Signal.id == signal_id)
        return self._session.scalars(statement).unique().first()

    def list(
        self, scope: DataScope, filters: SignalFilter, page: PageRequest
    ) -> SignalPage:
        statement = self._scoped(scope)

        if filters.hospital_id is not None:
            statement = statement.where(Signal.hospital_id == filters.hospital_id)
        if filters.region_id is not None:
            statement = statement.where(
                (Signal.region_id == filters.region_id)
                | (Hospital.region_id == filters.region_id)
            )
        if filters.status is not None:
            statement = statement.where(Signal.status == filters.status)
        if filters.severity is not None:
            statement = statement.where(Signal.severity == filters.severity)
        if filters.signal_type is not None:
            statement = statement.where(Signal.type == filters.signal_type)
        if filters.date_from is not None:
            statement = statement.where(Signal.detected_at >= filters.date_from)
        if filters.date_to is not None:
            statement = statement.where(Signal.detected_at <= filters.date_to)
        if filters.assigned_user_id is not None:
            statement = statement.where(
                Signal.assigned_user_id == filters.assigned_user_id
            )
        if filters.scope_type is not None:
            statement = statement.where(Signal.scope_type == filters.scope_type)

        total = count_of(self._session, statement)
        statement = apply_sort(statement, page, SIGNAL_SORT_COLUMNS)
        rows = (
            self._session.scalars(statement.offset(page.offset).limit(page.limit))
            .unique()
            .all()
        )
        return list(rows), total

    # ------------------------------------------------------------------
    # Изменение с проверкой версии
    # ------------------------------------------------------------------

    def _apply_versioned(
        self, signal_id: uuid.UUID, expected_version: int, values: dict[str, object]
    ) -> Signal | None:
        """Обновить строку, только если версия не изменилась.

        Возвращает None при расхождении версии. Условие входит в сам
        UPDATE: проверка отдельным SELECT оставила бы окно, в котором
        параллельная транзакция успеет записать своё изменение.
        """
        statement = (
            update(Signal)
            .where(Signal.id == signal_id, Signal.version == expected_version)
            .values(**values, version=Signal.version + 1)
            .returning(Signal.id)
        )
        updated_id = self._session.execute(statement).scalar_one_or_none()
        if updated_id is None:
            return None

        # Объект уже в сессии мог остаться со старой версией: перечитываем,
        # чтобы вызывающая сторона увидела фактическое состояние.
        self._session.expire_all()
        return self._session.get(Signal, signal_id)

    def update_status(
        self,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        new_status: SignalStatus,
        closed_reason: str | None,
        closed_at: datetime | None,
        closure_disposition: SignalClosureDisposition | None,
        now: datetime,
    ) -> Signal | None:
        return self._apply_versioned(
            signal_id,
            expected_version,
            {
                "status": new_status,
                "closed_reason": closed_reason,
                "closed_at": closed_at,
                "closure_disposition": closure_disposition,
                "updated_at": now,
            },
        )

    def update_assignment(
        self,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        assigned_user_id: uuid.UUID | None,
        now: datetime,
    ) -> Signal | None:
        return self._apply_versioned(
            signal_id,
            expected_version,
            {"assigned_user_id": assigned_user_id, "updated_at": now},
        )

    def add_if_absent(self, signal: Signal) -> tuple[Signal, bool]:
        """Insert within a savepoint and absorb only a real dedup race."""
        try:
            with self._session.begin_nested():
                self._session.add(signal)
                self._session.flush()
        except IntegrityError:
            existing = self.find_by_dedup_key(signal.dedup_key)
            if existing is None:
                raise
            return existing, False
        return signal, True

    def find_by_dedup_key(self, dedup_key: str) -> Signal | None:
        return self._session.scalar(select(Signal).where(Signal.dedup_key == dedup_key))

    def link_incident(
        self,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        incident_id: uuid.UUID,
        now: datetime,
    ) -> Signal | None:
        return self._apply_versioned(
            signal_id,
            expected_version,
            {"incident_id": incident_id, "updated_at": now},
        )
