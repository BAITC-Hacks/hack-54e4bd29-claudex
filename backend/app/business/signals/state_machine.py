"""Конечный автомат сигнала.

Единственное место, где описано, какие переходы допустимы. Frontend
не решает этого самостоятельно: он показывает то, что вернул сервер
(BUSINESS_LOGIC.md, раздел 4.5).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import ConflictError, ValidationError
from app.models.enums import SignalStatus

# Допустимые переходы. CLOSED не возвращается в NEW: сигнал, закрытый
# человеком, не может «расследоваться заново» с чистого листа — для
# возобновления существует переход в работу.
ALLOWED_TRANSITIONS: dict[SignalStatus, frozenset[SignalStatus]] = {
    SignalStatus.NEW: frozenset({SignalStatus.IN_PROGRESS, SignalStatus.CLOSED}),
    SignalStatus.IN_PROGRESS: frozenset({SignalStatus.CLOSED}),
    SignalStatus.CLOSED: frozenset({SignalStatus.IN_PROGRESS}),
}

# Переходы, требующие указания причины. Закрытие — управленческий факт,
# он должен быть объясним (BR-04).
REASON_REQUIRED_FOR: frozenset[SignalStatus] = frozenset(
    {SignalStatus.CLOSED, SignalStatus.IN_PROGRESS}
)

MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class TransitionRequest:
    current: SignalStatus
    target: SignalStatus
    reason: str | None


def available_transitions(current: SignalStatus) -> tuple[SignalStatus, ...]:
    """Переходы, допустимые из текущего состояния.

    Права роли здесь не учитываются: их накладывает сервис, у которого
    есть контекст пользователя.
    """
    return tuple(sorted(ALLOWED_TRANSITIONS.get(current, frozenset())))


def is_allowed(current: SignalStatus, target: SignalStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def validate_transition(request: TransitionRequest) -> str | None:
    """Проверить переход и вернуть нормализованную причину.

    Недопустимый переход даёт конфликт состояния, а не ошибку валидации:
    запрос корректен, но неприменим к текущему состоянию объекта.
    """
    if request.current == request.target:
        raise ConflictError(
            "Сигнал уже находится в этом состоянии",
            details={"status": request.current.value},
        )

    if not is_allowed(request.current, request.target):
        raise ConflictError(
            "Недопустимый переход состояния",
            details={
                "from": request.current.value,
                "to": request.target.value,
                "allowed": [s.value for s in available_transitions(request.current)],
            },
        )

    reason = (request.reason or "").strip()

    if request.target in REASON_REQUIRED_FOR:
        if len(reason) < MIN_REASON_LENGTH:
            raise ValidationError(
                "Для этого перехода необходимо указать причину",
                details={
                    "to": request.target.value,
                    "min_length": MIN_REASON_LENGTH,
                },
            )
        if len(reason) > MAX_REASON_LENGTH:
            raise ValidationError(
                "Причина слишком длинная",
                details={"max_length": MAX_REASON_LENGTH},
            )

    return reason or None
