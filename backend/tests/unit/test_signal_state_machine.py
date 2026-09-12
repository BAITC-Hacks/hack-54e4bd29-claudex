"""Конечный автомат сигнала.

Проверяется то, что образует смысл жизненного цикла: какие переходы
допустимы, какие требуют причины и почему закрытый сигнал не может
вернуться в начальное состояние.
"""

from __future__ import annotations

import pytest

from app.business.signals.state_machine import (
    TransitionRequest,
    available_transitions,
    is_allowed,
    validate_transition,
)
from app.core.exceptions import ConflictError, ValidationError
from app.models.enums import SignalStatus

NEW = SignalStatus.NEW
IN_PROGRESS = SignalStatus.IN_PROGRESS
CLOSED = SignalStatus.CLOSED


@pytest.mark.parametrize(
    ("current", "target"),
    [(NEW, IN_PROGRESS), (IN_PROGRESS, CLOSED), (NEW, CLOSED)],
)
def test_allowed_transitions(current: SignalStatus, target: SignalStatus) -> None:
    assert is_allowed(current, target)


def test_closed_cannot_return_to_new() -> None:
    """Закрытый сигнал не возвращается в начальное состояние.

    Закрытие — зафиксированный управленческий факт. Для возобновления
    работы существует переход в работу, а не сброс истории.
    """
    assert not is_allowed(CLOSED, NEW)


def test_closed_may_be_reopened_into_work() -> None:
    assert is_allowed(CLOSED, IN_PROGRESS)


def test_in_progress_cannot_go_back_to_new() -> None:
    assert not is_allowed(IN_PROGRESS, NEW)


def test_available_transitions_are_sorted_and_complete() -> None:
    assert available_transitions(NEW) == (CLOSED, IN_PROGRESS)
    assert available_transitions(IN_PROGRESS) == (CLOSED,)
    assert available_transitions(CLOSED) == (IN_PROGRESS,)


def test_transition_to_same_status_is_conflict() -> None:
    with pytest.raises(ConflictError):
        validate_transition(TransitionRequest(current=NEW, target=NEW, reason="x"))


def test_forbidden_transition_reports_allowed_options() -> None:
    """Отказ должен подсказывать, что вообще возможно из этого состояния."""
    with pytest.raises(ConflictError) as error:
        validate_transition(
            TransitionRequest(current=CLOSED, target=NEW, reason="возобновить")
        )
    assert error.value.details["allowed"] == ["IN_PROGRESS"]


@pytest.mark.parametrize("target", [IN_PROGRESS, CLOSED])
def test_reason_is_required(target: SignalStatus) -> None:
    """Переход без причины недопустим: решение должно быть объяснимо."""
    with pytest.raises(ValidationError):
        validate_transition(TransitionRequest(current=NEW, target=target, reason=None))


def test_blank_reason_is_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_transition(TransitionRequest(current=NEW, target=CLOSED, reason="   "))


def test_overlong_reason_is_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_transition(
            TransitionRequest(current=NEW, target=CLOSED, reason="я" * 1001)
        )


def test_reason_is_normalized() -> None:
    reason = validate_transition(
        TransitionRequest(current=NEW, target=CLOSED, reason="  данные устарели  ")
    )
    assert reason == "данные устарели"
