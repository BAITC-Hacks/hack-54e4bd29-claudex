"""Acceptance-only network readiness gate for ClickHouse migrations.

The helper runs inside the generated Compose ``data`` network.  It sends a
bounded ``SELECT 1`` using credentials from the container environment and
emits only fixed diagnostic fields; raw responses and exception text are
never logged.
"""

from __future__ import annotations

import base64
import errno
import math
import os
import re
import socket
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 32
DEFAULT_REQUEST_TIMEOUT_SECONDS = 2.0
DEFAULT_DEADLINE_SECONDS = 90.0
DEFAULT_RETRY_INTERVAL_SECONDS = 0.5
HOST_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*")
RETRYABLE_NETWORK_ERRNOS = frozenset(
    {
        errno.ECONNABORTED,
        errno.ECONNREFUSED,
        errno.ECONNRESET,
        errno.EHOSTUNREACH,
        errno.ENETDOWN,
        errno.ENETUNREACH,
        errno.EPIPE,
        errno.ETIMEDOUT,
    }
)

EXIT_READY = 0
EXIT_DEADLINE = 1
EXIT_HTTP = 2
EXIT_RESPONSE = 3
EXIT_CONFIG = 4
EXIT_NETWORK = 5


class _ReadDeadlineError(TimeoutError):
    """The complete response body exceeded the remaining overall budget."""


@dataclass(frozen=True)
class ReadinessConfig:
    host: str
    port: int
    username: str
    password: str
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS
    retry_interval_seconds: float = DEFAULT_RETRY_INTERVAL_SECONDS

    @classmethod
    def from_environment(cls) -> ReadinessConfig:
        config = cls(
            host=os.environ.get("CLICKHOUSE_HOST", "clickhouse"),
            port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
            username=os.environ.get("CLICKHOUSE_USER", ""),
            password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
            request_timeout_seconds=float(
                os.environ.get(
                    "CLICKHOUSE_READY_REQUEST_TIMEOUT_SECONDS",
                    str(DEFAULT_REQUEST_TIMEOUT_SECONDS),
                )
            ),
            deadline_seconds=float(
                os.environ.get(
                    "CLICKHOUSE_READY_DEADLINE_SECONDS",
                    str(DEFAULT_DEADLINE_SECONDS),
                )
            ),
            retry_interval_seconds=float(
                os.environ.get(
                    "CLICKHOUSE_READY_RETRY_INTERVAL_SECONDS",
                    str(DEFAULT_RETRY_INTERVAL_SECONDS),
                )
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if HOST_PATTERN.fullmatch(self.host) is None:
            raise ValueError("invalid ClickHouse host")
        if not 1 <= self.port <= 65535:
            raise ValueError("invalid ClickHouse port")
        if not self.username or not self.password:
            raise ValueError("missing ClickHouse credentials")
        if not all(
            math.isfinite(value)
            for value in (self.request_timeout_seconds, self.deadline_seconds)
        ) or (self.request_timeout_seconds <= 0 or self.deadline_seconds <= 0):
            raise ValueError("invalid ClickHouse timeout")
        if not math.isfinite(self.retry_interval_seconds) or (
            self.retry_interval_seconds < 0
        ):
            raise ValueError("invalid ClickHouse retry interval")


def _elapsed_ms(start: float, monotonic: Callable[[], float]) -> int:
    return max(0, round((monotonic() - start) * 1000))


def _retryable_network_error(error: BaseException) -> bool:
    if isinstance(error, HTTPError):
        return False
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, PermissionError):
        return False
    if isinstance(reason, socket.gaierror):
        return reason.errno == socket.EAI_AGAIN
    if isinstance(reason, TimeoutError | ConnectionError):
        return True
    return isinstance(reason, OSError) and reason.errno in RETRYABLE_NETWORK_ERRNOS


def _request(config: ReadinessConfig) -> Request:
    credentials = f"{config.username}:{config.password}".encode()
    authorization = base64.b64encode(credentials).decode("ascii")
    return Request(
        f"http://{config.host}:{config.port}/",
        data=b"SELECT 1",
        headers={
            "Authorization": f"Basic {authorization}",
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="POST",
    )


def _read_bounded_body(
    response: Any,
    *,
    deadline: float,
    monotonic: Callable[[], float],
) -> bytes:
    """Bound the complete response read, not only each underlying socket read."""
    body: list[bytes] = []
    errors: list[Exception] = []

    def read_response() -> None:
        try:
            body.append(response.read(MAX_RESPONSE_BYTES + 1))
        except Exception as error:  # pragma: no cover - re-raised in caller thread
            errors.append(error)

    worker = threading.Thread(
        target=read_response,
        name="clickhouse-readiness-response",
        daemon=True,
    )
    worker.start()
    worker.join(max(0.0, deadline - monotonic()))
    if worker.is_alive():
        close = getattr(response, "close", None)
        if callable(close):
            with suppress(OSError):
                close()
        raise _ReadDeadlineError("ClickHouse readiness deadline exceeded")
    if errors:
        raise errors[0]
    if not body:
        raise OSError("ClickHouse readiness response read failed")
    return body[0]


def wait_until_ready(
    config: ReadinessConfig,
    *,
    open_url: Callable[..., Any] = urlopen,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    emit: Callable[[str], None] = print,
) -> int:
    """Wait for a network-visible ``SELECT 1`` and return a stable exit code."""
    config.validate()
    start = monotonic()
    deadline = start + config.deadline_seconds
    attempts = 0
    emit("CLICKHOUSE_READY_START elapsed_ms=0 attempts=0 category=STARTED")

    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            emit(
                "CLICKHOUSE_READY_FAIL "
                f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
                "category=DEADLINE_EXCEEDED http_status=none"
            )
            return EXIT_DEADLINE

        attempts += 1
        try:
            with open_url(
                _request(config),
                timeout=min(config.request_timeout_seconds, remaining),
            ) as response:
                status = int(response.status)
                declared_length = response.headers.get("Content-Length")
                body = _read_bounded_body(
                    response,
                    deadline=deadline,
                    monotonic=monotonic,
                )
        except _ReadDeadlineError:
            emit(
                "CLICKHOUSE_READY_FAIL "
                f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
                "category=DEADLINE_EXCEEDED http_status=none"
            )
            return EXIT_DEADLINE
        except HTTPError as error:
            emit(
                "CLICKHOUSE_READY_FAIL "
                f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
                f"category=HTTP_ERROR http_status={error.code}"
            )
            return EXIT_HTTP
        except (OSError, URLError) as error:
            if not _retryable_network_error(error):
                emit(
                    "CLICKHOUSE_READY_FAIL "
                    f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
                    "category=NETWORK_ERROR http_status=none"
                )
                return EXIT_NETWORK
            if monotonic() >= deadline:
                emit(
                    "CLICKHOUSE_READY_FAIL "
                    f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
                    "category=DEADLINE_EXCEEDED http_status=none"
                )
                return EXIT_DEADLINE
            emit(
                "CLICKHOUSE_READY_RETRY "
                f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
                "category=NETWORK_TRANSIENT http_status=none"
            )
            sleep(min(config.retry_interval_seconds, max(0.0, deadline - monotonic())))
            continue

        if monotonic() > deadline:
            emit(
                "CLICKHOUSE_READY_FAIL "
                f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
                "category=DEADLINE_EXCEEDED http_status=none"
            )
            return EXIT_DEADLINE
        if status != 200:
            emit(
                "CLICKHOUSE_READY_FAIL "
                f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
                f"category=HTTP_ERROR http_status={status}"
            )
            return EXIT_HTTP
        try:
            expected_length = (
                int(declared_length) if declared_length is not None else None
            )
        except ValueError:
            expected_length = -1
        if expected_length is not None and (
            expected_length < 0 or expected_length != len(body)
        ):
            emit(
                "CLICKHOUSE_READY_FAIL "
                f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
                "category=INCOMPLETE_RESPONSE http_status=200 "
                f"response_bytes={len(body)}"
            )
            return EXIT_RESPONSE
        if len(body) > MAX_RESPONSE_BYTES or body.strip() != b"1":
            emit(
                "CLICKHOUSE_READY_FAIL "
                f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
                f"category=UNEXPECTED_RESPONSE http_status=200 response_bytes={len(body)}"
            )
            return EXIT_RESPONSE

        emit(
            "CLICKHOUSE_READY_OK "
            f"elapsed_ms={_elapsed_ms(start, monotonic)} attempts={attempts} "
            f"category=READY http_status=200 response_bytes={len(body)}"
        )
        return EXIT_READY


def main() -> int:
    try:
        config = ReadinessConfig.from_environment()
    except (TypeError, ValueError):
        print(
            "CLICKHOUSE_READY_FAIL elapsed_ms=0 attempts=0 "
            "category=CONFIG_ERROR http_status=none"
        )
        return EXIT_CONFIG
    return wait_until_ready(config)


if __name__ == "__main__":
    raise SystemExit(main())
