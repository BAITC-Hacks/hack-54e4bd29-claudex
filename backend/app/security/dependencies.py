"""Зависимости FastAPI для аутентификации и проверки прав."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenError, UnauthenticatedError
from app.security.context import Role, SecurityContext
from app.security.oidc import get_authentication_service

# auto_error=False: собственный контракт ошибки вместо стандартного
# ответа FastAPI (API.md, раздел 1.2).
_bearer_scheme = HTTPBearer(auto_error=False, scheme_name="Keycloak OIDC")


def get_security_context(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
) -> SecurityContext:
    """Контекст доступа текущего пользователя.

    Отсутствие или недействительность токена приводит к отказу.
    Запасного пути аутентификации не существует.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthenticatedError("Требуется токен доступа")

    context = get_authentication_service().authenticate(credentials.credentials)
    # Идентификатор субъекта попадает в журнал; персональные данные — нет.
    request.state.user_id = context.user_id
    return context


CurrentUser = Annotated[SecurityContext, Depends(get_security_context)]


def require_roles(*roles: Role) -> Callable[[SecurityContext], SecurityContext]:
    """Зависимость, требующая одну из перечисленных ролей.

    Проверяется право на операцию. Область данных проверяется отдельно,
    в бизнес-слое, где известен объект (ADR-0006).
    """
    allowed = frozenset(roles)

    def dependency(context: CurrentUser) -> SecurityContext:
        if not context.has_role(*allowed):
            raise ForbiddenError(
                "Недостаточно прав для выполнения операции",
                details={"required_roles": sorted(role.value for role in allowed)},
            )
        return context

    return dependency
