"""HTTP-посредники: идентификатор запроса, журнал доступа, заголовки безопасности."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.logging import get_logger
from app.core.request_context import (
    REQUEST_ID_HEADER,
    reset_request_id,
    sanitize_request_id,
    set_request_id,
)

logger = get_logger("medsignal.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Присваивает запросу идентификатор и пишет запись журнала доступа.

    В журнал попадают метод, путь, код ответа и длительность. Строка запроса,
    заголовки и тело не логируются: они могут содержать чувствительные данные.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = sanitize_request_id(request.headers.get(REQUEST_ID_HEADER))
        token = set_request_id(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "Запрос завершился исключением",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            reset_request_id(token)
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "Запрос обработан",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        reset_request_id(token)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Заголовки безопасности на уровне приложения.

    Основной рубеж — обратный прокси (SECURITY.md, раздел 6.1). Здесь они
    дублируются, чтобы приложение оставалось защищённым и при прямом доступе,
    например в тестах или при ошибке конфигурации прокси.
    """

    def __init__(self, app: ASGIApp, *, force_https: bool) -> None:
        super().__init__(app)
        self._force_https = force_https

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        headers.setdefault("Cache-Control", "no-store")
        if self._force_https:
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
