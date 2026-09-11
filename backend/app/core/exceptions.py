"""Исключения приложения.

Модуль не импортирует веб-фреймворк и не содержит кодов HTTP: бизнес-слой
не знает о протоколе доставки (ARCHITECTURE.md, раздел 5.3). Отображение
кода ошибки на код ответа выполняет слой API.
"""

from __future__ import annotations

from typing import Any

# Сообщение при непредвиденной ошибке. Одно и то же во всех случаях:
# различия в тексте раскрывают устройство системы.
INTERNAL_ERROR_MESSAGE = "Внутренняя ошибка сервера. Обратитесь к администратору."


class AppError(Exception):
    """Базовая ошибка приложения.

    Несёт машиночитаемый код и сообщение для пользователя. Подробности
    для диагностики остаются в журнале, а не в этом объекте.
    """

    code: str = "INTERNAL_ERROR"
    message: str = INTERNAL_ERROR_MESSAGE

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    message = "Запрос не прошёл проверку"


class NotFoundError(AppError):
    """Объект не найден либо находится вне области данных пользователя.

    Одна ошибка для двух случаев — сознательное решение ADR-0006:
    отдельный ответ подтверждал бы существование объекта.
    """

    code = "NOT_FOUND"
    message = "Объект не найден"


class UnauthenticatedError(AppError):
    code = "UNAUTHENTICATED"
    message = "Требуется аутентификация"


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    message = "Недостаточно прав для выполнения операции"


class ConflictError(AppError):
    code = "CONFLICT"
    message = "Операция невозможна в текущем состоянии объекта"


class DependencyUnavailableError(AppError):
    code = "DEPENDENCY_UNAVAILABLE"
    message = "Сервис временно недоступен"
