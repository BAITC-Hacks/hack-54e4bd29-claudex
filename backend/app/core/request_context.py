"""Контекст текущего запроса.

`request_id` сопровождает операцию от HTTP-запроса до фоновой задачи,
попадает в каждую запись журнала и возвращается клиенту в заголовке.
Это основа диагностики и разбора инцидентов (SECURITY.md, раздел 12).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

REQUEST_ID_HEADER = "X-Request-ID"

# Идентификатор приходит извне, поэтому принимается только безопасная форма:
# это значение попадает в журнал и в заголовок ответа.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{8,128}$")

_request_id: ContextVar[str | None] = ContextVar("medsignal_request_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def sanitize_request_id(raw: str | None) -> str:
    """Принять внешний идентификатор или выдать новый.

    Непригодное значение не вызывает ошибку: запрос обслуживается,
    но с собственным идентификатором.
    """
    if raw and _SAFE_REQUEST_ID.match(raw):
        return raw
    return new_request_id()


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


@contextmanager
def request_id_scope(value: str) -> Iterator[str]:
    """Установить идентификатор на время блока.

    Используется воркером Celery, который получает идентификатор
    вместе с задачей и должен вернуть контекст в исходное состояние.
    """
    token = set_request_id(value)
    try:
        yield value
    finally:
        reset_request_id(token)
