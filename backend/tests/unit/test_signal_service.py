"""Правила работы с сигналами на уровне бизнес-сервиса.

Проверяется то, ради чего сервис существует: переходы состояния,
назначение ответственного, обнаружение одновременного изменения,
применение области данных и запись в журнал аудита.
"""

from __future__ import annotations

import uuid

import pytest

from app.business.shared.events import EventDispatcher, SignalStatusChanged
from app.business.signals.service import SIGNAL_DEFAULT_SORT, SignalService
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import AuditAction, SignalStatus
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role
from app.shared.filters import SignalFilter
from app.shared.pagination import PageRequest
from tests.fakes import (
    FakeStore,
    make_context,
    make_hospital,
    make_region,
    make_signal,
    make_user,
    unit_of_work_factory,
)


@pytest.fixture
def dispatcher() -> EventDispatcher:
    return EventDispatcher()


@pytest.fixture
def service(store: FakeStore, dispatcher: EventDispatcher) -> SignalService:
    return SignalService(unit_of_work_factory(store), AuthorizationService(), dispatcher)


@pytest.fixture
def world(store: FakeStore):
    """Два региона, три организации, по сигналу на каждую."""

    class World:
        pass

    world = World()
    world.region_a = store.add_region(make_region("R-A", "Регион А"))
    world.region_b = store.add_region(make_region("R-B", "Регион Б"))
    world.hospital_a1 = store.add_hospital(make_hospital(world.region_a, "H-A1"))
    world.hospital_a2 = store.add_hospital(make_hospital(world.region_a, "H-A2"))
    world.hospital_b1 = store.add_hospital(make_hospital(world.region_b, "H-B1"))
    world.signal_a1 = store.add_signal(make_signal(world.hospital_a1))
    world.signal_a2 = store.add_signal(make_signal(world.hospital_a2))
    world.signal_b1 = store.add_signal(make_signal(world.hospital_b1))
    return world


def manager_in(store: FakeStore, hospital_id: uuid.UUID):
    user = store.add_user(
        make_user(f"manager-{hospital_id}"),
        DataScope(hospital_ids=frozenset({str(hospital_id)}), resolved=True),
    )
    return make_context(
        roles={Role.HOSPITAL_MANAGER},
        scope=store.user_scopes[user.id],
        user=user,
    )


def analyst_in_region(store: FakeStore, region_id: uuid.UUID):
    user = store.add_user(
        make_user(f"analyst-{region_id}"),
        DataScope(region_ids=frozenset({str(region_id)}), resolved=True),
    )
    return make_context(
        roles={Role.REGIONAL_ANALYST},
        scope=store.user_scopes[user.id],
        user=user,
    )


PAGE = PageRequest(page=1, page_size=20, sort_by=SIGNAL_DEFAULT_SORT, sort_desc=True)


# --- Переходы состояния -----------------------------------------------------


def test_new_to_in_progress(service: SignalService, store: FakeStore, world) -> None:
    context = manager_in(store, world.hospital_a1.id)
    detail = service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.IN_PROGRESS,
        expected_version=1,
        reason="взято в работу",
    )
    assert detail.signal.status == SignalStatus.IN_PROGRESS


def test_in_progress_to_closed(service: SignalService, store: FakeStore, world) -> None:
    context = manager_in(store, world.hospital_a1.id)
    service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.IN_PROGRESS,
        expected_version=1,
        reason="взято в работу",
    )
    detail = service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.CLOSED,
        expected_version=2,
        reason="ситуация отработана",
    )
    assert detail.signal.status == SignalStatus.CLOSED
    assert detail.signal.closed_reason == "ситуация отработана"
    assert detail.signal.closed_at is not None


def test_new_to_closed_directly(service: SignalService, store: FakeStore, world) -> None:
    context = manager_in(store, world.hospital_a1.id)
    detail = service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.CLOSED,
        expected_version=1,
        reason="ложное срабатывание",
    )
    assert detail.signal.status == SignalStatus.CLOSED


def test_closed_to_new_is_denied(service: SignalService, store: FakeStore, world) -> None:
    context = manager_in(store, world.hospital_a1.id)
    service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.CLOSED,
        expected_version=1,
        reason="ложное срабатывание",
    )
    with pytest.raises(ConflictError):
        service.change_status(
            context,
            world.signal_a1.id,
            target_status=SignalStatus.NEW,
            expected_version=2,
            reason="вернуть",
        )


def test_analyst_cannot_change_status(
    service: SignalService, store: FakeStore, world
) -> None:
    user = store.add_user(
        make_user("analyst"),
        DataScope(hospital_ids=frozenset({str(world.hospital_a1.id)}), resolved=True),
    )
    context = make_context(
        roles={Role.HOSPITAL_ANALYST}, scope=store.user_scopes[user.id], user=user
    )
    with pytest.raises(ForbiddenError):
        service.change_status(
            context,
            world.signal_a1.id,
            target_status=SignalStatus.IN_PROGRESS,
            expected_version=1,
            reason="взять",
        )


def test_analyst_sees_no_available_transitions(
    service: SignalService, store: FakeStore, world
) -> None:
    """Перечень переходов зависит от роли и приходит с сервера."""
    user = store.add_user(
        make_user("analyst-view"),
        DataScope(hospital_ids=frozenset({str(world.hospital_a1.id)}), resolved=True),
    )
    context = make_context(
        roles={Role.HOSPITAL_ANALYST}, scope=store.user_scopes[user.id], user=user
    )
    detail = service.get_signal(context, world.signal_a1.id)
    assert detail.available_transitions == ()


def test_manager_sees_transitions(
    service: SignalService, store: FakeStore, world
) -> None:
    context = manager_in(store, world.hospital_a1.id)
    detail = service.get_signal(context, world.signal_a1.id)
    assert SignalStatus.IN_PROGRESS in detail.available_transitions


# --- Одновременное изменение ------------------------------------------------


def test_stale_version_is_conflict(
    service: SignalService, store: FakeStore, world
) -> None:
    """Второй сотрудник не затирает решение первого молча."""
    context = manager_in(store, world.hospital_a1.id)
    service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.IN_PROGRESS,
        expected_version=1,
        reason="первый взял",
    )
    with pytest.raises(ConflictError) as error:
        service.change_status(
            context,
            world.signal_a1.id,
            target_status=SignalStatus.CLOSED,
            expected_version=1,
            reason="второй закрывает по устаревшей карточке",
        )
    assert error.value.details["expected_version"] == 1


def test_version_increases_on_each_change(
    service: SignalService, store: FakeStore, world
) -> None:
    context = manager_in(store, world.hospital_a1.id)
    assert world.signal_a1.version == 1
    service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.IN_PROGRESS,
        expected_version=1,
        reason="в работу",
    )
    assert world.signal_a1.version == 2


# --- Назначение ответственного ----------------------------------------------


def test_assign_within_scope(service: SignalService, store: FakeStore, world) -> None:
    context = manager_in(store, world.hospital_a1.id)
    assignee = store.add_user(
        make_user("assignee"),
        DataScope(hospital_ids=frozenset({str(world.hospital_a1.id)}), resolved=True),
    )
    detail = service.assign(
        context, world.signal_a1.id, assignee_id=assignee.id, expected_version=1
    )
    assert detail.signal.assigned_user_id == assignee.id


def test_assignee_outside_scope_is_rejected(
    service: SignalService, store: FakeStore, world
) -> None:
    """Назначение того, кто не видит сигнал, создаёт невыполнимую задачу."""
    context = manager_in(store, world.hospital_a1.id)
    outsider = store.add_user(
        make_user("outsider"),
        DataScope(hospital_ids=frozenset({str(world.hospital_b1.id)}), resolved=True),
    )
    with pytest.raises(ValidationError):
        service.assign(
            context, world.signal_a1.id, assignee_id=outsider.id, expected_version=1
        )


def test_assign_unknown_user_is_rejected(
    service: SignalService, store: FakeStore, world
) -> None:
    context = manager_in(store, world.hospital_a1.id)
    with pytest.raises(ValidationError):
        service.assign(
            context, world.signal_a1.id, assignee_id=uuid.uuid4(), expected_version=1
        )


def test_unassign_clears_responsible(
    service: SignalService, store: FakeStore, world
) -> None:
    context = manager_in(store, world.hospital_a1.id)
    assignee = store.add_user(
        make_user("assignee-2"),
        DataScope(hospital_ids=frozenset({str(world.hospital_a1.id)}), resolved=True),
    )
    service.assign(
        context, world.signal_a1.id, assignee_id=assignee.id, expected_version=1
    )
    detail = service.unassign(context, world.signal_a1.id, expected_version=2)
    assert detail.signal.assigned_user_id is None


def test_assignment_conflict_on_stale_version(
    service: SignalService, store: FakeStore, world
) -> None:
    context = manager_in(store, world.hospital_a1.id)
    assignee = store.add_user(
        make_user("assignee-3"),
        DataScope(hospital_ids=frozenset({str(world.hospital_a1.id)}), resolved=True),
    )
    service.assign(
        context, world.signal_a1.id, assignee_id=assignee.id, expected_version=1
    )
    with pytest.raises(ConflictError):
        service.assign(
            context, world.signal_a1.id, assignee_id=assignee.id, expected_version=1
        )


# --- Область данных ---------------------------------------------------------


def test_hospital_user_cannot_read_other_hospital(
    service: SignalService, store: FakeStore, world
) -> None:
    context = manager_in(store, world.hospital_a1.id)
    with pytest.raises(NotFoundError):
        service.get_signal(context, world.signal_a2.id)


def test_regional_user_cannot_read_other_region(
    service: SignalService, store: FakeStore, world
) -> None:
    context = analyst_in_region(store, world.region_a.id)
    with pytest.raises(NotFoundError):
        service.get_signal(context, world.signal_b1.id)


def test_regional_user_sees_all_hospitals_of_own_region(
    service: SignalService, store: FakeStore, world
) -> None:
    context = analyst_in_region(store, world.region_a.id)
    page = service.list_signals(context, SignalFilter(), PAGE)
    assert {item.id for item in page.items} == {
        world.signal_a1.id,
        world.signal_a2.id,
    }


def test_unresolved_scope_sees_nothing(
    service: SignalService, store: FakeStore, world
) -> None:
    """Ненастроенная область данных — это запрет, а не полный доступ."""
    context = make_context(roles={Role.HOSPITAL_MANAGER}, scope=DataScope.unresolved())
    page = service.list_signals(context, SignalFilter(), PAGE)
    assert page.items == []
    assert page.total == 0


def test_admin_sees_everything(service: SignalService, store: FakeStore, world) -> None:
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope())
    page = service.list_signals(context, SignalFilter(), PAGE)
    assert page.total == 3


def test_status_change_outside_scope_is_not_found(
    service: SignalService, store: FakeStore, world
) -> None:
    """Запись тоже ограничена областью, а не только чтение."""
    context = manager_in(store, world.hospital_a1.id)
    with pytest.raises(NotFoundError):
        service.change_status(
            context,
            world.signal_b1.id,
            target_status=SignalStatus.IN_PROGRESS,
            expected_version=1,
            reason="чужой сигнал",
        )


# --- Аудит и события --------------------------------------------------------


def test_status_change_writes_audit(
    service: SignalService, store: FakeStore, world
) -> None:
    context = manager_in(store, world.hospital_a1.id)
    service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.IN_PROGRESS,
        expected_version=1,
        reason="в работу",
    )
    events = [e for e in store.audit if e.action == AuditAction.SIGNAL_STATUS_CHANGED]
    assert len(events) == 1
    assert events[0].entity_id == world.signal_a1.id
    assert events[0].actor_user_id == context.internal_user_id
    assert events[0].event_metadata["from"] == "NEW"
    assert events[0].event_metadata["to"] == "IN_PROGRESS"


def test_assignment_writes_audit(service: SignalService, store: FakeStore, world) -> None:
    context = manager_in(store, world.hospital_a1.id)
    assignee = store.add_user(
        make_user("assignee-4"),
        DataScope(hospital_ids=frozenset({str(world.hospital_a1.id)}), resolved=True),
    )
    service.assign(
        context, world.signal_a1.id, assignee_id=assignee.id, expected_version=1
    )
    assert any(e.action == AuditAction.SIGNAL_ASSIGNED for e in store.audit)


def test_unassignment_writes_audit(
    service: SignalService, store: FakeStore, world
) -> None:
    context = manager_in(store, world.hospital_a1.id)
    service.unassign(context, world.signal_a1.id, expected_version=1)
    assert any(e.action == AuditAction.SIGNAL_UNASSIGNED for e in store.audit)


def test_failed_transition_writes_no_audit(
    service: SignalService, store: FakeStore, world
) -> None:
    """Отклонённая операция не оставляет следа об изменении."""
    context = manager_in(store, world.hospital_a1.id)
    with pytest.raises(ConflictError):
        service.change_status(
            context,
            world.signal_a1.id,
            target_status=SignalStatus.NEW,
            expected_version=1,
            reason="повтор",
        )
    assert store.audit == []


def test_status_change_records_human_action(
    service: SignalService, store: FakeStore, world
) -> None:
    context = manager_in(store, world.hospital_a1.id)
    service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.IN_PROGRESS,
        expected_version=1,
        reason="принято к работе",
    )
    assert len(store.actions) == 1
    assert store.actions[0].created_by == context.internal_user_id


def test_domain_event_published_after_commit(
    store: FakeStore, world, dispatcher: EventDispatcher
) -> None:
    """Событие рассылается только после фиксации операции."""
    seen: list[SignalStatusChanged] = []
    dispatcher.subscribe(SignalStatusChanged, lambda e: seen.append(e))  # type: ignore[arg-type]
    service = SignalService(
        unit_of_work_factory(store), AuthorizationService(), dispatcher
    )
    context = manager_in(store, world.hospital_a1.id)

    service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.IN_PROGRESS,
        expected_version=1,
        reason="в работу",
    )

    assert len(seen) == 1
    assert seen[0].to_status == SignalStatus.IN_PROGRESS
    assert store.commits >= 1


# --- Фильтрация -------------------------------------------------------------


def test_filter_by_status(service: SignalService, store: FakeStore, world) -> None:
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope())
    service.change_status(
        context,
        world.signal_a1.id,
        target_status=SignalStatus.IN_PROGRESS,
        expected_version=1,
        reason="в работу",
    )
    page = service.list_signals(
        context, SignalFilter(status=SignalStatus.IN_PROGRESS), PAGE
    )
    assert [item.id for item in page.items] == [world.signal_a1.id]


def test_filter_by_hospital(service: SignalService, store: FakeStore, world) -> None:
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope())
    page = service.list_signals(
        context, SignalFilter(hospital_id=world.hospital_b1.id), PAGE
    )
    assert [item.id for item in page.items] == [world.signal_b1.id]


def test_invalid_period_is_rejected(service: SignalService, store: FakeStore) -> None:
    from datetime import UTC, datetime

    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope())
    filters = SignalFilter(
        date_from=datetime(2026, 5, 1, tzinfo=UTC),
        date_to=datetime(2026, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ValidationError):
        service.list_signals(context, filters, PAGE)
