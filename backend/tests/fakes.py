"""Подмены хранилища для тестов бизнес-правил.

Правила проверяются без СУБД: так тест падает из-за нарушенного правила,
а не из-за окружения. Подмены повторяют наблюдаемое поведение настоящих
репозиториев, включая два места, где ошибиться проще всего:

* фильтрацию по области данных;
* условное обновление по версии.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any

from app.models.access import User
from app.models.action import Action
from app.models.audit import AuditEvent
from app.models.directory import Hospital, Region
from app.models.enums import (
    AuditAction,
    AuditEntityType,
    SignalSeverity,
    SignalSourceType,
    SignalStatus,
    SignalType,
)
from app.models.incident import Incident
from app.models.signal import Signal
from app.security.context import DataScope, Role, SecurityContext
from app.shared.filters import AuditFilter, HospitalFilter, IncidentFilter, SignalFilter
from app.shared.pagination import PageRequest


def _now() -> datetime:
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Построители объектов
# ---------------------------------------------------------------------------


def make_region(code: str = "R-A", name: str = "Регион А") -> Region:
    return Region(
        id=uuid.uuid4(),
        code=code,
        name=name,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def make_hospital(
    region: Region, code: str = "H-1", name: str = "Больница 1"
) -> Hospital:
    hospital = Hospital(
        id=uuid.uuid4(),
        code=code,
        name=name,
        region_id=region.id,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )
    # Связь заполняется вручную: без сессии ленивые загрузки недоступны.
    hospital.region = region
    return hospital


def make_signal(
    hospital: Hospital,
    *,
    status: SignalStatus = SignalStatus.NEW,
    severity: SignalSeverity = SignalSeverity.WARNING,
    signal_type: SignalType = SignalType.QUEUE_GROWTH,
    version: int = 1,
    detected_at: datetime | None = None,
    assigned_user_id: uuid.UUID | None = None,
) -> Signal:
    signal = Signal(
        id=uuid.uuid4(),
        hospital_id=hospital.id,
        type=signal_type,
        severity=severity,
        status=status,
        source_type=SignalSourceType.STATISTICAL,
        title="Синтетический сигнал",
        summary="Создан для проверки правил",
        detected_at=detected_at or _now(),
        created_at=_now(),
        updated_at=_now(),
        version=version,
        assigned_user_id=assigned_user_id,
    )
    signal.hospital = hospital
    signal.explanation = None
    return signal


def make_user(subject: str = "subject-1") -> User:
    return User(
        id=uuid.uuid4(),
        external_subject=subject,
        display_name=subject,
        email=None,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def make_context(
    *,
    roles: set[Role],
    scope: DataScope | None = None,
    user: User | None = None,
) -> SecurityContext:
    actor = user or make_user()
    return SecurityContext(
        user_id=actor.external_subject,
        roles=frozenset(roles),
        scope=scope or DataScope.unresolved(),
        internal_user_id=actor.id,
    )


# ---------------------------------------------------------------------------
# Хранилище в памяти
# ---------------------------------------------------------------------------


class FakeStore:
    """Общее состояние между единицами работы одного теста."""

    def __init__(self) -> None:
        self.regions: dict[uuid.UUID, Region] = {}
        self.hospitals: dict[uuid.UUID, Hospital] = {}
        self.signals: dict[uuid.UUID, Signal] = {}
        self.incidents: dict[uuid.UUID, Incident] = {}
        self.actions: list[Action] = []
        self.audit: list[AuditEvent] = []
        self.users: dict[uuid.UUID, User] = {}
        self.user_scopes: dict[uuid.UUID, DataScope] = {}
        self.commits = 0

    def add_region(self, region: Region) -> Region:
        self.regions[region.id] = region
        return region

    def add_hospital(self, hospital: Hospital) -> Hospital:
        self.hospitals[hospital.id] = hospital
        return hospital

    def add_signal(self, signal: Signal) -> Signal:
        self.signals[signal.id] = signal
        return signal

    def add_user(self, user: User, scope: DataScope | None = None) -> User:
        self.users[user.id] = user
        self.user_scopes[user.id] = scope or DataScope.unresolved()
        return user


def _visible_hospital(scope: DataScope, hospital: Hospital | None) -> bool:
    """Повторяет условие области данных из слоя репозиториев."""
    if scope.is_global:
        return True
    if not scope.resolved or hospital is None:
        return False
    if str(hospital.id) in scope.hospital_ids:
        return True
    return str(hospital.region_id) in scope.region_ids


def _paginate[T](items: list[T], page: PageRequest) -> tuple[list[T], int]:
    total = len(items)
    start = page.offset
    return items[start : start + page.limit], total


class FakeRegionRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def _visible(self, scope: DataScope) -> list[Region]:
        if scope.is_global:
            return list(self._store.regions.values())
        if not scope.resolved:
            return []
        allowed = set(scope.region_ids)
        allowed |= {
            str(h.region_id)
            for h in self._store.hospitals.values()
            if str(h.id) in scope.hospital_ids
        }
        return [r for r in self._store.regions.values() if str(r.id) in allowed]

    def get(self, region_id: uuid.UUID, scope: DataScope) -> Region | None:
        return next((r for r in self._visible(scope) if r.id == region_id), None)

    def list(self, scope: DataScope, page: PageRequest) -> tuple[list[Region], int]:
        return _paginate(sorted(self._visible(scope), key=lambda r: r.name), page)


class FakeHospitalRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def _visible(self, scope: DataScope) -> list[Hospital]:
        return [h for h in self._store.hospitals.values() if _visible_hospital(scope, h)]

    def get(self, hospital_id: uuid.UUID, scope: DataScope) -> Hospital | None:
        return next((h for h in self._visible(scope) if h.id == hospital_id), None)

    def list(
        self, scope: DataScope, filters: HospitalFilter, page: PageRequest
    ) -> tuple[list[Hospital], int]:
        items = self._visible(scope)
        if filters.region_id is not None:
            items = [h for h in items if h.region_id == filters.region_id]
        if filters.is_active is not None:
            items = [h for h in items if h.is_active == filters.is_active]
        return _paginate(sorted(items, key=lambda h: h.name), page)


class FakeSignalRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def _visible(self, scope: DataScope) -> list[Signal]:
        return [
            s
            for s in self._store.signals.values()
            if _visible_hospital(scope, self._store.hospitals.get(s.hospital_id))
        ]

    def get(self, signal_id: uuid.UUID, scope: DataScope) -> Signal | None:
        return next((s for s in self._visible(scope) if s.id == signal_id), None)

    def list(
        self, scope: DataScope, filters: SignalFilter, page: PageRequest
    ) -> tuple[list[Signal], int]:
        items = self._visible(scope)
        if filters.hospital_id is not None:
            items = [s for s in items if s.hospital_id == filters.hospital_id]
        if filters.region_id is not None:
            items = [
                s
                for s in items
                if self._store.hospitals[s.hospital_id].region_id == filters.region_id
            ]
        if filters.status is not None:
            items = [s for s in items if s.status == filters.status]
        if filters.severity is not None:
            items = [s for s in items if s.severity == filters.severity]
        if filters.signal_type is not None:
            items = [s for s in items if s.type == filters.signal_type]
        if filters.date_from is not None:
            items = [s for s in items if s.detected_at >= filters.date_from]
        if filters.date_to is not None:
            items = [s for s in items if s.detected_at <= filters.date_to]
        if filters.assigned_user_id is not None:
            items = [s for s in items if s.assigned_user_id == filters.assigned_user_id]
        items = sorted(items, key=lambda s: s.detected_at, reverse=page.sort_desc)
        return _paginate(items, page)

    def _versioned(self, signal_id: uuid.UUID, expected_version: int) -> Signal | None:
        """Повторяет условное обновление: несовпадение версии — отказ."""
        signal = self._store.signals.get(signal_id)
        if signal is None or signal.version != expected_version:
            return None
        signal.version += 1
        return signal

    def update_status(
        self,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        new_status: SignalStatus,
        closed_reason: str | None,
        closed_at: datetime | None,
        now: datetime,
    ) -> Signal | None:
        signal = self._versioned(signal_id, expected_version)
        if signal is None:
            return None
        signal.status = new_status
        signal.closed_reason = closed_reason
        signal.closed_at = closed_at
        signal.updated_at = now
        return signal

    def update_assignment(
        self,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        assigned_user_id: uuid.UUID | None,
        now: datetime,
    ) -> Signal | None:
        signal = self._versioned(signal_id, expected_version)
        if signal is None:
            return None
        signal.assigned_user_id = assigned_user_id
        signal.updated_at = now
        return signal

    def add(self, signal: Signal) -> Signal:
        self._store.signals[signal.id] = signal
        return signal


class FakeIncidentRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def _visible(self, scope: DataScope) -> list[Incident]:
        return [
            i
            for i in self._store.incidents.values()
            if _visible_hospital(scope, self._store.hospitals.get(i.hospital_id))
        ]

    def get(self, incident_id: uuid.UUID, scope: DataScope) -> Incident | None:
        return next((i for i in self._visible(scope) if i.id == incident_id), None)

    def list(
        self, scope: DataScope, filters: IncidentFilter, page: PageRequest
    ) -> tuple[list[Incident], int]:
        items = self._visible(scope)
        if filters.hospital_id is not None:
            items = [i for i in items if i.hospital_id == filters.hospital_id]
        if filters.status is not None:
            items = [i for i in items if i.status == filters.status]
        return _paginate(items, page)

    def signals_of(self, incident_id: uuid.UUID, scope: DataScope) -> list[Signal]:
        return [
            s
            for s in self._store.signals.values()
            if s.incident_id == incident_id
            and _visible_hospital(scope, self._store.hospitals.get(s.hospital_id))
        ]


class FakeActionRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def add(self, action: Action) -> Action:
        if action.id is None:
            action.id = uuid.uuid4()
        action.created_at = action.created_at or _now()
        self._store.actions.append(action)
        return action

    def list_for_signal(self, signal_id: uuid.UUID) -> list[Action]:
        return [a for a in self._store.actions if a.signal_id == signal_id]


class FakeAuditRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

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
            id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id,
            event_metadata=metadata,
            created_at=_now() + timedelta(microseconds=len(self._store.audit)),
        )
        self._store.audit.append(event)
        return event

    def list(
        self, scope: DataScope, filters: AuditFilter, page: PageRequest
    ) -> tuple[list[AuditEvent], int]:
        visible_signals = {
            s.id
            for s in self._store.signals.values()
            if _visible_hospital(scope, self._store.hospitals.get(s.hospital_id))
        }
        items = [
            e
            for e in self._store.audit
            if scope.is_global
            or (
                e.entity_type == AuditEntityType.SIGNAL and e.entity_id in visible_signals
            )
        ]
        if filters.entity_id is not None:
            items = [e for e in items if e.entity_id == filters.entity_id]
        if filters.action is not None:
            items = [e for e in items if e.action == filters.action]
        return _paginate(items, page)

    def list_for_entity(
        self, entity_type: AuditEntityType, entity_id: uuid.UUID, *, limit: int
    ) -> list[AuditEvent]:
        return [
            e
            for e in self._store.audit
            if e.entity_type == entity_type and e.entity_id == entity_id
        ][:limit]


class FakeUserRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def get(self, user_id: uuid.UUID) -> User | None:
        return self._store.users.get(user_id)

    def get_by_subject(self, external_subject: str) -> User | None:
        return next(
            (
                u
                for u in self._store.users.values()
                if u.external_subject == external_subject
            ),
            None,
        )

    def ensure(
        self, *, external_subject: str, display_name: str | None, email: str | None
    ) -> User:
        existing = self.get_by_subject(external_subject)
        if existing is not None:
            return existing
        user = make_user(external_subject)
        user.display_name = display_name
        user.email = email
        return self._store.add_user(user)

    def resolve_scope(self, user: User) -> DataScope:
        return self._store.user_scopes.get(user.id, DataScope.unresolved())


class FakeUnitOfWork:
    """Единица работы в памяти.

    Фиксация считается: тест может проверить, что операция и запись
    аудита сохранены вместе, а не по отдельности.
    """

    def __init__(self, store: FakeStore) -> None:
        self._store = store
        self.regions = FakeRegionRepository(store)
        self.hospitals = FakeHospitalRepository(store)
        self.signals = FakeSignalRepository(store)
        self.incidents = FakeIncidentRepository(store)
        self.actions = FakeActionRepository(store)
        self.audit = FakeAuditRepository(store)
        self.users = FakeUserRepository(store)

    def __enter__(self) -> FakeUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        self._store.commits += 1

    def rollback(self) -> None:
        return None

    def flush(self) -> None:
        return None


def unit_of_work_factory(store: FakeStore):
    def factory() -> FakeUnitOfWork:
        return FakeUnitOfWork(store)

    return factory
