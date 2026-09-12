"""Доменные события.

Лёгкий механизм внутри процесса: брокера сообщений здесь нет и пока
не нужно. Назначение — дать точку подключения будущим уведомлениям,
не размазывая их вызовы по бизнес-коду.

События собираются в ходе транзакции и публикуются только после
успешной фиксации. Обработчик, увидевший событие о незафиксированном
изменении, рассылал бы уведомления о том, чего не произошло.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.logging import get_logger
from app.models.enums import SignalSeverity, SignalStatus, SignalType

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Базовое событие предметной области."""

    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class SignalCreated(DomainEvent):
    signal_id: uuid.UUID = field(kw_only=True)
    hospital_id: uuid.UUID = field(kw_only=True)
    signal_type: SignalType = field(kw_only=True)
    severity: SignalSeverity = field(kw_only=True)


@dataclass(frozen=True, slots=True)
class SignalStatusChanged(DomainEvent):
    signal_id: uuid.UUID = field(kw_only=True)
    from_status: SignalStatus = field(kw_only=True)
    to_status: SignalStatus = field(kw_only=True)
    actor_id: uuid.UUID = field(kw_only=True)


@dataclass(frozen=True, slots=True)
class SignalClosed(DomainEvent):
    signal_id: uuid.UUID = field(kw_only=True)
    reason: str = field(kw_only=True)
    actor_id: uuid.UUID = field(kw_only=True)


@dataclass(frozen=True, slots=True)
class SignalAssigned(DomainEvent):
    signal_id: uuid.UUID = field(kw_only=True)
    assignee_id: uuid.UUID = field(kw_only=True)
    actor_id: uuid.UUID = field(kw_only=True)


@dataclass(frozen=True, slots=True)
class SignalUnassigned(DomainEvent):
    signal_id: uuid.UUID = field(kw_only=True)
    previous_assignee_id: uuid.UUID | None = field(kw_only=True)
    actor_id: uuid.UUID = field(kw_only=True)


EventHandler = Callable[[DomainEvent], None]


class EventDispatcher:
    """Рассылка событий подписчикам внутри процесса."""

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, events: list[DomainEvent]) -> None:
        """Разослать события.

        Отказ обработчика не откатывает уже зафиксированную операцию
        и не срывает остальные обработки: событие вторично по отношению
        к самому изменению.
        """
        for event in events:
            for handler in self._handlers.get(type(event), ()):
                try:
                    handler(event)
                except Exception as exc:
                    logger.error(
                        "Обработчик события завершился ошибкой",
                        extra={"event_type": type(event).__name__},
                        exc_info=exc,
                    )


class EventCollector:
    """Накопитель событий одной операции."""

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    def add(self, event: DomainEvent) -> None:
        self._events.append(event)

    def drain(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events


_dispatcher = EventDispatcher()


def get_event_dispatcher() -> EventDispatcher:
    return _dispatcher
