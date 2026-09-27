"""Отображение исключений на ответы API.

Клиент всегда получает одну и ту же форму ответа:

    {"error": {"code": ..., "message": ..., "details": ..., "request_id": ...}}

Трассировка и внутренние имена наружу не уходят никогда: они остаются
в журнале, связанном по `request_id` (API.md, раздел 1.2).

Знание об HTTP сосредоточено здесь. Исключения приложения кодов ответа
не содержат — это позволяет бизнес-слою не зависеть от протокола.
"""

from __future__ import annotations

from typing import Any, Final

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import INTERNAL_ERROR_MESSAGE, AppError
from app.core.logging import get_logger, redact
from app.core.request_context import get_request_id

logger = get_logger(__name__)

# Код ошибки приложения -> код ответа HTTP.
ERROR_CODE_TO_STATUS: Final[dict[str, int]] = {
    "VALIDATION_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "UNAUTHENTICATED": status.HTTP_401_UNAUTHORIZED,
    "FORBIDDEN": status.HTTP_403_FORBIDDEN,
    "CONFLICT": status.HTTP_409_CONFLICT,
    "DEPENDENCY_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
    "COPILOT_DISABLED": status.HTTP_503_SERVICE_UNAVAILABLE,
    "COPILOT_INSUFFICIENT_DATA": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "COPILOT_PROVIDER_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
    "COPILOT_PROVIDER_TIMEOUT": status.HTTP_504_GATEWAY_TIMEOUT,
    "COPILOT_INVALID_RESPONSE": status.HTTP_502_BAD_GATEWAY,
    "COPILOT_RATE_LIMITED": status.HTTP_429_TOO_MANY_REQUESTS,
    "INTERNAL_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
}

# Код ответа HTTP -> код ошибки приложения, для исключений фреймворка.
STATUS_TO_ERROR_CODE: Final[dict[int, str]] = {
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    429: "RATE_LIMIT_EXCEEDED",
}


def build_error_response(
    *,
    code: str,
    message: str,
    http_status: int,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": redact(details or {}),
            "request_id": get_request_id(),
        }
    }
    return JSONResponse(status_code=http_status, content=body, headers=headers)


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    http_status = ERROR_CODE_TO_STATUS.get(
        exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    headers = (
        {"WWW-Authenticate": "Bearer"}
        if http_status == status.HTTP_401_UNAUTHORIZED
        else None
    )

    if http_status >= 500:
        logger.error("Ошибка приложения", extra={"error_code": exc.code}, exc_info=exc)
    else:
        logger.info(
            "Запрос отклонён",
            extra={"error_code": exc.code, "http_status": http_status},
        )

    return build_error_response(
        code=exc.code,
        message=exc.message,
        http_status=http_status,
        details=exc.details,
        headers=headers,
    )


async def _handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = STATUS_TO_ERROR_CODE.get(exc.status_code, "HTTP_ERROR")

    fallback = "Запрос не может быть выполнен"
    message = exc.detail if isinstance(exc.detail, str) else fallback
    if exc.status_code >= 500:
        message = INTERNAL_ERROR_MESSAGE

    headers = dict(exc.headers) if exc.headers else None
    return build_error_response(
        code=code, message=message, http_status=exc.status_code, headers=headers
    )


async def _handle_request_validation(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())[1:]),
            "reason": error.get("msg", ""),
        }
        for error in exc.errors()
    ]
    return build_error_response(
        code="VALIDATION_ERROR",
        message="Запрос не прошёл проверку",
        http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"fields": fields},
    )


async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    """Последний рубеж: наружу уходит только общее сообщение."""
    logger.error("Необработанное исключение", exc_info=exc)
    return build_error_response(
        code="INTERNAL_ERROR",
        message=INTERNAL_ERROR_MESSAGE,
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
