"""Общие схемы ответов API."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ItemT = TypeVar("ItemT")


class ErrorDetail(BaseModel):
    """Содержимое поля `error` в ответе об ошибке."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="Машиночитаемый код ошибки")
    message: str = Field(description="Сообщение для пользователя")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Уточнения без внутренних деталей системы"
    )
    request_id: str | None = Field(
        default=None, description="Идентификатор запроса для диагностики"
    )


class ErrorResponse(BaseModel):
    """Единый контракт ошибки для всех эндпоинтов."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


class Page(BaseModel, Generic[ItemT]):
    """Постраничный ответ.

    Неограниченная выдача не поддерживается ни одним эндпоинтом
    (API.md, раздел 1.1).
    """

    items: list[ItemT]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    has_next: bool


# Описания ответов для OpenAPI. Подключаются к маршрутам, чтобы
# контракт ошибки был виден в документации, а не только в коде.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Некорректный запрос"},
    401: {"model": ErrorResponse, "description": "Не аутентифицирован"},
    403: {"model": ErrorResponse, "description": "Недостаточно прав"},
    404: {"model": ErrorResponse, "description": "Объект не найден"},
    422: {"model": ErrorResponse, "description": "Ошибка валидации"},
    500: {"model": ErrorResponse, "description": "Внутренняя ошибка"},
    503: {"model": ErrorResponse, "description": "Зависимость недоступна"},
}
