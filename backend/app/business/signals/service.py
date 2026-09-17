"""Правила работы с сигналами.

Сервис — единственное место, где решается, что можно сделать с сигналом.
Ни маршрут, ни репозиторий, ни модель этих правил не содержат.

Три сквозных требования выполняются здесь:

* область данных применяется к каждому обращению (ADR-0006);
* бизнес-операция и запись аудита фиксируются одной транзакцией;
* одновременное изменение обнаруживается по версии, а не затирается.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.business.ports import UnitOfWorkFactory
from app.business.shared.events import (
    DomainEvent,
    EventCollector,
    EventDispatcher,
    SignalAssigned,
    SignalClosed,
    SignalStatusChanged,
    SignalUnassigned,
)
from app.business.signals.state_machine import (
    TransitionRequest,
    available_transitions,
    validate_transition,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.request_context import get_request_id
from app.models.action import Action
from app.models.audit import AuditEvent
from app.models.enums import (
    ActionType,
    AuditAction,
    AuditEntityType,
    DataScopeType,
    SignalClosureDisposition,
    SignalStatus,
)
from app.models.signal import Signal
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, SecurityContext
from app.security.permissions import Permission
from app.shared.filters import SignalFilter
from app.shared.pagination import Page, PageRequest

logger = get_logger(__name__)

# Поля, по которым разрешена сортировка ленты. Произвольное имя поля
# извне в запрос не попадает.
SIGNAL_SORT_FIELDS: frozenset[str] = frozenset(
    {"detected_at", "created_at", "severity", "status", "type"}
)
SIGNAL_DEFAULT_SORT = "detected_at"


@dataclass(frozen=True, slots=True)
class SignalDetail:
    """Карточка сигнала вместе с тем, что зависит от контекста доступа."""

    signal: Signal
    available_transitions: tuple[SignalStatus, ...]
    actions: list[Action]
    audit_events: list[AuditEvent]


def _now() -> datetime:
    return datetime.now(tz=UTC)


class SignalService:
    """Чтение ленты, карточка, смена статуса и назначение ответственного."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        authorization: AuthorizationService,
        dispatcher: EventDispatcher,
    ) -> None:
        self._uow_factory = uow_factory
        self._authz = authorization
        self._dispatcher = dispatcher

    # ------------------------------------------------------------------
    # Чтение
    # ------------------------------------------------------------------

    def list_signals(
        self, context: SecurityContext, filters: SignalFilter, page: PageRequest
    ) -> Page[Signal]:
        self._authz.require_permission(context, Permission.SIGNAL_READ)
        filters.validate()

        with self._uow_factory() as uow:
            items, total = uow.signals.list(context.scope, filters, page)
        return Page.build(items, total, page)

    def get_signal(self, context: SecurityContext, signal_id: uuid.UUID) -> SignalDetail:
        """Карточка сигнала.

        Объект вне области данных не отличим от отсутствующего: иначе
        перебором идентификаторов выясняется состав организаций.
        """
        self._authz.require_permission(context, Permission.SIGNAL_READ)

        with self._uow_factory() as uow:
            signal = uow.signals.get(signal_id, context.scope)
            if signal is None:
                raise NotFoundError("Сигнал не найден")

            actions = uow.actions.list_for_signal(signal_id)
            audit_events = uow.audit.list_for_entity(
                AuditEntityType.SIGNAL, signal_id, limit=50
            )
            transitions = self._transitions_for(context, SignalStatus(signal.status))

        return SignalDetail(
            signal=signal,
            available_transitions=transitions,
            actions=actions,
            audit_events=audit_events,
        )

    def _transitions_for(
        self, context: SecurityContext, current: SignalStatus
    ) -> tuple[SignalStatus, ...]:
        """Переходы, доступные именно этому пользователю.

        Аналитик организации видит пустой перечень: он исследует
        и объясняет, решение фиксирует руководитель.
        """
        if not self._authz.has_permission(context, Permission.SIGNAL_UPDATE_STATUS):
            return ()
        return available_transitions(current)

    # ------------------------------------------------------------------
    # Смена статуса
    # ------------------------------------------------------------------

    def change_status(
        self,
        context: SecurityContext,
        signal_id: uuid.UUID,
        *,
        target_status: SignalStatus,
        expected_version: int,
        reason: str | None,
    ) -> SignalDetail:
        return self._change_status(
            context,
            signal_id,
            target_status=target_status,
            expected_version=expected_version,
            reason=reason,
            disposition=(
                SignalClosureDisposition.RESOLVED
                if target_status is SignalStatus.CLOSED
                else None
            ),
            audit_action=AuditAction.SIGNAL_STATUS_CHANGED,
        )

    def acknowledge(
        self,
        context: SecurityContext,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        reason: str,
    ) -> SignalDetail:
        return self._change_status(
            context,
            signal_id,
            target_status=SignalStatus.IN_PROGRESS,
            expected_version=expected_version,
            reason=reason,
            disposition=None,
            audit_action=AuditAction.SIGNAL_ACKNOWLEDGED,
        )

    def resolve(
        self,
        context: SecurityContext,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        reason: str,
    ) -> SignalDetail:
        return self._change_status(
            context,
            signal_id,
            target_status=SignalStatus.CLOSED,
            expected_version=expected_version,
            reason=reason,
            disposition=SignalClosureDisposition.RESOLVED,
            audit_action=AuditAction.SIGNAL_RESOLVED,
        )

    def dismiss(
        self,
        context: SecurityContext,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        reason: str,
    ) -> SignalDetail:
        return self._change_status(
            context,
            signal_id,
            target_status=SignalStatus.CLOSED,
            expected_version=expected_version,
            reason=reason,
            disposition=SignalClosureDisposition.DISMISSED,
            audit_action=AuditAction.SIGNAL_DISMISSED,
        )

    def _change_status(
        self,
        context: SecurityContext,
        signal_id: uuid.UUID,
        *,
        target_status: SignalStatus,
        expected_version: int,
        reason: str | None,
        disposition: SignalClosureDisposition | None,
        audit_action: AuditAction,
    ) -> SignalDetail:
        self._authz.require_permission(context, Permission.SIGNAL_UPDATE_STATUS)
        events = EventCollector()

        with self._uow_factory() as uow:
            signal = uow.signals.get(signal_id, context.scope)
            if signal is None:
                raise NotFoundError("Сигнал не найден")

            current = SignalStatus(signal.status)
            normalized_reason = validate_transition(
                TransitionRequest(current=current, target=target_status, reason=reason)
            )

            now = _now()
            closing = target_status is SignalStatus.CLOSED
            updated = uow.signals.update_status(
                signal_id,
                expected_version=expected_version,
                new_status=target_status,
                closed_reason=normalized_reason if closing else None,
                closed_at=now if closing else None,
                closure_disposition=disposition if closing else None,
                now=now,
            )
            if updated is None:
                # Версия не совпала: между чтением и записью объект изменил
                # кто-то другой. Молча перезаписать его решение нельзя.
                raise ConflictError(
                    "Сигнал был изменён другим пользователем. Обновите карточку",
                    details={"expected_version": expected_version},
                )

            uow.actions.add(
                Action(
                    signal_id=signal_id,
                    created_by=context.actor_id,
                    action_type=ActionType.STATUS_CHANGE,
                    description=normalized_reason
                    or f"Статус изменён на {target_status.value}",
                )
            )
            uow.audit.append(
                actor_user_id=context.actor_id,
                action=audit_action,
                entity_type=AuditEntityType.SIGNAL,
                entity_id=signal_id,
                request_id=get_request_id(),
                metadata={
                    "from": current.value,
                    "to": target_status.value,
                    "reason": normalized_reason,
                    "disposition": disposition.value if disposition else None,
                },
            )
            uow.commit()

            events.add(
                SignalStatusChanged(
                    signal_id=signal_id,
                    from_status=current,
                    to_status=target_status,
                    actor_id=context.actor_id,
                )
            )
            if closing:
                events.add(
                    SignalClosed(
                        signal_id=signal_id,
                        reason=normalized_reason or "",
                        actor_id=context.actor_id,
                    )
                )

        self._publish(events.drain())
        return self.get_signal(context, signal_id)

    # ------------------------------------------------------------------
    # Назначение ответственного
    # ------------------------------------------------------------------

    def assign(
        self,
        context: SecurityContext,
        signal_id: uuid.UUID,
        *,
        assignee_id: uuid.UUID,
        expected_version: int,
    ) -> SignalDetail:
        self._authz.require_permission(context, Permission.SIGNAL_ASSIGN)
        events = EventCollector()

        with self._uow_factory() as uow:
            signal = uow.signals.get(signal_id, context.scope)
            if signal is None:
                raise NotFoundError("Сигнал не найден")

            assignee = uow.users.get(assignee_id)
            if assignee is None or not assignee.is_active:
                raise ValidationError("Указанный пользователь недоступен для назначения")

            # Ответственный обязан видеть сигнал. Назначение того, кто
            # не имеет доступа к организации, создаёт задачу, которую
            # невозможно выполнить.
            # The current actor's effective scope already includes OIDC role
            # semantics (ADMIN => GLOBAL). Roles are intentionally not copied
            # to PostgreSQL, so resolving only user_data_scopes would reject a
            # valid self-assignment. Other users remain fail-closed because
            # their live OIDC roles are unavailable in this request.
            assignee_scope = (
                context.scope
                if assignee.id == context.actor_id
                else uow.users.resolve_scope(assignee)
            )
            if not self._scope_covers_signal(assignee_scope, signal):
                raise ValidationError(
                    "Ответственный не имеет доступа к организации этого сигнала"
                )

            updated = uow.signals.update_assignment(
                signal_id,
                expected_version=expected_version,
                assigned_user_id=assignee_id,
                now=_now(),
            )
            if updated is None:
                raise ConflictError(
                    "Сигнал был изменён другим пользователем. Обновите карточку",
                    details={"expected_version": expected_version},
                )

            uow.actions.add(
                Action(
                    signal_id=signal_id,
                    created_by=context.actor_id,
                    action_type=ActionType.ASSIGNMENT,
                    description="Назначен ответственный",
                )
            )
            uow.audit.append(
                actor_user_id=context.actor_id,
                action=AuditAction.SIGNAL_ASSIGNED,
                entity_type=AuditEntityType.SIGNAL,
                entity_id=signal_id,
                request_id=get_request_id(),
                metadata={"assignee_id": str(assignee_id)},
            )
            uow.commit()
            events.add(
                SignalAssigned(
                    signal_id=signal_id,
                    assignee_id=assignee_id,
                    actor_id=context.actor_id,
                )
            )

        self._publish(events.drain())
        return self.get_signal(context, signal_id)

    def unassign(
        self, context: SecurityContext, signal_id: uuid.UUID, *, expected_version: int
    ) -> SignalDetail:
        self._authz.require_permission(context, Permission.SIGNAL_ASSIGN)
        events = EventCollector()

        with self._uow_factory() as uow:
            signal = uow.signals.get(signal_id, context.scope)
            if signal is None:
                raise NotFoundError("Сигнал не найден")

            previous = signal.assigned_user_id
            updated = uow.signals.update_assignment(
                signal_id,
                expected_version=expected_version,
                assigned_user_id=None,
                now=_now(),
            )
            if updated is None:
                raise ConflictError(
                    "Сигнал был изменён другим пользователем. Обновите карточку",
                    details={"expected_version": expected_version},
                )

            uow.actions.add(
                Action(
                    signal_id=signal_id,
                    created_by=context.actor_id,
                    action_type=ActionType.ASSIGNMENT,
                    description="Ответственный снят",
                )
            )
            uow.audit.append(
                actor_user_id=context.actor_id,
                action=AuditAction.SIGNAL_UNASSIGNED,
                entity_type=AuditEntityType.SIGNAL,
                entity_id=signal_id,
                request_id=get_request_id(),
                metadata={"previous_assignee_id": str(previous) if previous else None},
            )
            uow.commit()
            events.add(
                SignalUnassigned(
                    signal_id=signal_id,
                    previous_assignee_id=previous,
                    actor_id=context.actor_id,
                )
            )

        self._publish(events.drain())
        return self.get_signal(context, signal_id)

    # ------------------------------------------------------------------
    # Вспомогательное
    # ------------------------------------------------------------------

    @staticmethod
    def _scope_covers_signal(scope: DataScope, signal: Signal) -> bool:
        """Покрывает ли область данных explicit scope сигнала."""
        if scope.is_global:
            return True
        if not scope.resolved:
            return False
        scope_type = DataScopeType(signal.scope_type)
        if scope_type is DataScopeType.GLOBAL:
            return False
        if scope_type is DataScopeType.REGION:
            return (
                signal.region_id is not None and str(signal.region_id) in scope.region_ids
            )
        if (
            signal.hospital_id is not None
            and str(signal.hospital_id) in scope.hospital_ids
        ):
            return True
        region_id = getattr(signal.hospital, "region_id", None)
        return region_id is not None and str(region_id) in scope.region_ids

    def _publish(self, events: list[DomainEvent]) -> None:
        """Публикация после фиксации транзакции.

        До фиксации события рассылать нельзя: обработчик сообщил бы
        о том, чего ещё не произошло.
        """
        if events:
            self._dispatcher.publish(events)
