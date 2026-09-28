from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.business.incidents.service import IncidentService
from app.business.shared.events import EventDispatcher
from app.business.signals.service import SignalService
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.models.enums import (
    AuditAction,
    DataScopeType,
    IncidentStatus,
    SignalClosureDisposition,
    SignalSeverity,
    SignalSourceType,
    SignalStatus,
    SignalType,
)
from app.models.incident import Incident
from app.models.signal import Signal
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role
from app.shared.filters import IncidentFilter
from app.shared.pagination import PageRequest
from tests.fakes import (
    FakeIncidentRepository,
    FakeStore,
    make_context,
    make_user,
    unit_of_work_factory,
)


def _global_signal(store: FakeStore) -> Signal:
    now = datetime.now(tz=UTC)
    return store.add_signal(
        Signal(
            id=uuid.uuid4(),
            scope_type=DataScopeType.GLOBAL,
            region_id=None,
            hospital_id=None,
            type=SignalType.DATA_STALE,
            severity=SignalSeverity.WARNING,
            status=SignalStatus.NEW,
            source_type=SignalSourceType.RULE_BASED,
            title="Global signal",
            summary="Synthetic test signal",
            detected_at=now,
            created_at=now,
            updated_at=now,
            version=1,
            source="ИС БГ",
            rule_code="DATA_STALE_REFERRALS",
            rule_version="v1",
            rule_config={},
            evidence={},
            data_watermark={"import_ids": ["test"]},
            data_current=False,
            dedup_key=uuid.uuid4().hex + uuid.uuid4().hex,
        )
    )


def _admin(store: FakeStore):
    user = store.add_user(make_user("admin"), DataScope.global_scope())
    return make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=user)


def _services(store: FakeStore):
    factory = unit_of_work_factory(store)
    authz = AuthorizationService()
    return (
        SignalService(factory, authz, EventDispatcher()),
        IncidentService(factory, authz),
    )


def test_acknowledge_and_resolve_have_explicit_audit_actions(store: FakeStore) -> None:
    signal = _global_signal(store)
    context = _admin(store)
    service, _ = _services(store)

    acknowledged = service.acknowledge(
        context, signal.id, expected_version=1, reason="Проверка начата"
    )
    assert acknowledged.signal.status is SignalStatus.IN_PROGRESS
    resolved = service.resolve(
        context, signal.id, expected_version=2, reason="Поставка восстановлена"
    )

    assert resolved.signal.status is SignalStatus.CLOSED
    assert resolved.signal.closure_disposition is SignalClosureDisposition.RESOLVED
    assert [event.action for event in store.audit] == [
        AuditAction.SIGNAL_ACKNOWLEDGED,
        AuditAction.SIGNAL_RESOLVED,
    ]


def test_dismiss_records_disposition_and_reason(store: FakeStore) -> None:
    signal = _global_signal(store)
    context = _admin(store)
    service, _ = _services(store)

    detail = service.dismiss(
        context, signal.id, expected_version=1, reason="Не требует обработки"
    )

    assert detail.signal.status is SignalStatus.CLOSED
    assert detail.signal.closure_disposition is SignalClosureDisposition.DISMISSED
    assert store.audit[-1].action is AuditAction.SIGNAL_DISMISSED


def test_analyst_cannot_acknowledge_signal(store: FakeStore) -> None:
    signal = _global_signal(store)
    analyst = store.add_user(make_user("analyst"), DataScope.global_scope())
    context = make_context(
        roles={Role.HOSPITAL_ANALYST}, scope=DataScope.global_scope(), user=analyst
    )
    service, _ = _services(store)

    with pytest.raises(ForbiddenError):
        service.acknowledge(
            context, signal.id, expected_version=1, reason="Попытка изменения"
        )


def test_create_incident_from_signal_is_traceable_and_idempotent(
    store: FakeStore,
) -> None:
    signal = _global_signal(store)
    context = _admin(store)
    _, incidents = _services(store)

    created = incidents.create_from_signal(
        context,
        signal.id,
        expected_signal_version=1,
        title="Проверка поставки данных",
        description="Требуется связаться с владельцем источника",
    )
    repeated = incidents.create_from_signal(
        context,
        signal.id,
        expected_signal_version=2,
        title="Повторный запрос",
        description=None,
    )

    assert len(store.incidents) == 1
    assert created.incident.id == repeated.incident.id
    assert signal.incident_id == created.incident.id
    assert created.incident.scope_type is DataScopeType.GLOBAL
    assert created.incident.created_by == context.actor_id
    assert (
        sum(
            event.action is AuditAction.INCIDENT_CREATED_FROM_SIGNAL
            for event in store.audit
        )
        == 1
    )


def test_incident_assignment_and_status_are_versioned_and_audited(
    store: FakeStore,
) -> None:
    signal = _global_signal(store)
    context = _admin(store)
    assignee = store.add_user(make_user("authority"), DataScope.global_scope())
    _, incidents = _services(store)
    created = incidents.create_from_signal(
        context,
        signal.id,
        expected_signal_version=1,
        title="Инцидент",
        description=None,
    )

    assigned = incidents.assign(
        context,
        created.incident.id,
        assignee_id=assignee.id,
        expected_version=1,
    )
    closed = incidents.change_status(
        context,
        created.incident.id,
        target_status=IncidentStatus.CLOSED,
        expected_version=2,
        reason="Контроль завершён",
    )

    assert assigned.incident.assigned_user_id == assignee.id
    assert closed.incident.status is IncidentStatus.CLOSED
    assert AuditAction.INCIDENT_ASSIGNED in [item.action for item in store.audit]
    assert AuditAction.INCIDENT_STATUS_CHANGED in [item.action for item in store.audit]

    with pytest.raises(ConflictError):
        incidents.change_status(
            context,
            created.incident.id,
            target_status=IncidentStatus.OPEN,
            expected_version=1,
            reason="Старая версия",
        )


def test_global_incident_cannot_be_assigned_to_non_global_user(
    store: FakeStore,
) -> None:
    signal = _global_signal(store)
    context = _admin(store)
    assignee = store.add_user(
        make_user("regional"),
        DataScope(region_ids=frozenset({str(uuid.uuid4())}), resolved=True),
    )
    _, incidents = _services(store)
    created = incidents.create_from_signal(
        context,
        signal.id,
        expected_signal_version=1,
        title="Инцидент",
        description=None,
    )

    with pytest.raises(ValidationError, match="области"):
        incidents.assign(
            context,
            created.incident.id,
            assignee_id=assignee.id,
            expected_version=1,
        )


def test_admin_can_assign_global_signal_to_self_without_persisted_scope(
    store: FakeStore,
) -> None:
    """ADMIN effective scope comes from OIDC role, not user_data_scopes."""
    signal = _global_signal(store)
    admin = store.add_user(make_user("oidc-admin"), DataScope.unresolved())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=admin)
    signals, _ = _services(store)

    assigned = signals.assign(
        context,
        signal.id,
        assignee_id=admin.id,
        expected_version=1,
    )

    assert assigned.signal.assigned_user_id == admin.id


def test_admin_can_assign_global_incident_to_self_without_persisted_scope(
    store: FakeStore,
) -> None:
    signal = _global_signal(store)
    admin = store.add_user(make_user("oidc-admin-incident"), DataScope.unresolved())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=admin)
    _, incidents = _services(store)
    created = incidents.create_from_signal(
        context,
        signal.id,
        expected_signal_version=1,
        title="Инцидент",
        description=None,
    )

    assigned = incidents.assign(
        context,
        created.incident.id,
        assignee_id=admin.id,
        expected_version=1,
    )

    assert assigned.incident.assigned_user_id == admin.id


def test_region_filter_includes_explicit_region_scoped_incident(
    store: FakeStore,
) -> None:
    region_id = uuid.uuid4()
    now = datetime.now(tz=UTC)
    matching = Incident(
        id=uuid.uuid4(),
        scope_type=DataScopeType.REGION,
        region_id=region_id,
        hospital_id=None,
        title="Региональный инцидент",
        status=IncidentStatus.OPEN,
        version=1,
        created_at=now,
        updated_at=now,
    )
    other = Incident(
        id=uuid.uuid4(),
        scope_type=DataScopeType.GLOBAL,
        region_id=None,
        hospital_id=None,
        title="Глобальный инцидент",
        status=IncidentStatus.OPEN,
        version=1,
        created_at=now,
        updated_at=now,
    )
    store.incidents[matching.id] = matching
    store.incidents[other.id] = other

    items, total = FakeIncidentRepository(store).list(
        DataScope.global_scope(),
        IncidentFilter(region_id=region_id),
        PageRequest(page=1, page_size=20, sort_by="created_at", sort_desc=True),
    )

    assert total == 1
    assert [item.id for item in items] == [matching.id]
