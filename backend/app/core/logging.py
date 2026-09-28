"""Структурированное журналирование.

Два обязательных свойства (SECURITY.md, раздел 9.2):

1. Каждая запись содержит `request_id`, если он известен.
2. Чувствительные значения не попадают в журнал никогда.

Второе реализовано фильтром, а не дисциплиной разработчиков: полагаться
на то, что никто не запишет заголовок Authorization, нельзя.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Final

from app.core.request_context import get_request_id

# Ключи, значения которых заменяются маркером. Сравнение нечувствительно
# к регистру и выполняется по вхождению подстроки: `x-authorization`,
# `access_token` и `user_password` должны попасть под правило.
SENSITIVE_KEY_PARTS: Final[frozenset[str]] = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "password",
        "passwd",
        "secret",
        "token",
        "api-key",
        "apikey",
        "access-key",
        "private-key",
        "session",
        "credential",
        "salt",
        # Прямые идентификаторы: в журнал не попадают даже случайно.
        "iin",
        "ssn",
        "patient",
        "full-name",
        "fullname",
        "phone",
        "birth",
    }
)

REDACTED: Final[str] = "[redacted]"

# Атрибуты LogRecord, которые не являются пользовательскими полями.
_RESERVED_ATTRS: Final[frozenset[str]] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def _is_sensitive(key: str) -> bool:
    normalized = key.lower().replace("_", "-")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def redact(value: Any, _depth: int = 0) -> Any:
    """Рекурсивно заменить чувствительные значения маркером."""
    if _depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive(str(key)) else redact(item, _depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [redact(item, _depth + 1) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Форматирует запись журнала в одну строку JSON."""

    def __init__(self, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service,
            "environment": self._environment,
        }

        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key in _RESERVED_ATTRS or key.startswith("_"):
                continue
            if key in payload:
                continue
            payload[key] = REDACTED if _is_sensitive(key) else redact(value)

        if record.exc_info:
            # Трассировка остаётся в журнале, но никогда не уходит клиенту.
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Читаемый формат для локальной разработки."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = get_request_id()
        suffix = f" [{request_id[:8]}]" if request_id else ""
        return f"{record.levelname:<8}{suffix} {record.name}: {record.getMessage()}" + (
            f"\n{self.formatException(record.exc_info)}" if record.exc_info else ""
        )


class RedactingFilter(logging.Filter):
    """Подстраховка для чужого кода, пишущего словари в `extra`."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__):
            if key in _RESERVED_ATTRS or key.startswith("_"):
                continue
            if _is_sensitive(key):
                record.__dict__[key] = REDACTED
        return True


def configure_logging(*, level: str, fmt: str, service: str, environment: str) -> None:
    """Настроить корневой журнал процесса.

    Вызывается один раз при старте приложения и воркера.
    """
    formatter: logging.Formatter = (
        JsonFormatter(service=service, environment=environment)
        if fmt == "json"
        else ConsoleFormatter()
    )

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Доступ uvicorn дублирует наш журнал запросов — оставляем один источник.
    logging.getLogger("uvicorn.access").disabled = True
    for noisy in ("uvicorn.error", "sqlalchemy.engine", "urllib3", "httpx"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
