"""Служба авторизации.

Отвечает на два разных вопроса, и делает это раздельно (ADR-0006):

1. «Имеет ли роль право на операцию» — проверяется до обращения к данным.
   Отказ даёт 403: пользователь не имеет права на такое действие вообще.
2. «Относится ли объект к области данных пользователя» — проверяется там,
   где объект известен. Отказ даёт 404: ответ 403 подтвердил бы
   существование объекта и позволил бы перебором выяснить состав
   организаций региона.
"""

from __future__ import annotations

import uuid

from app.core.exceptions import ForbiddenError, NotFoundError
from app.security.context import SecurityContext
from app.security.permissions import Permission, permissions_for


class AuthorizationService:
    """Проверки прав и области данных. Состояния не имеет."""

    def has_permission(self, context: SecurityContext, permission: Permission) -> bool:
        return permission in permissions_for(context.roles)

    def require_permission(
        self, context: SecurityContext, permission: Permission
    ) -> None:
        """Отказать, если у роли нет права на операцию."""
        if not self.has_permission(context, permission):
            raise ForbiddenError(
                "Недостаточно прав для выполнения операции",
                details={"required_permission": permission.value},
            )

    def granted_permissions(self, context: SecurityContext) -> frozenset[Permission]:
        return permissions_for(context.roles)

    # ------------------------------------------------------------------
    # Область данных
    # ------------------------------------------------------------------

    def require_hospital_access(
        self,
        context: SecurityContext,
        hospital_id: uuid.UUID,
        region_id: uuid.UUID | None = None,
    ) -> None:
        """Отказать, если организация вне области данных пользователя.

        Возбуждается NotFoundError, а не ForbiddenError: различие ответов
        раскрывало бы существование объекта.
        """
        allowed = context.can_access_hospital(
            str(hospital_id), str(region_id) if region_id else None
        )
        if not allowed:
            raise NotFoundError("Объект не найден")

    def require_region_access(
        self, context: SecurityContext, region_id: uuid.UUID
    ) -> None:
        if not context.can_access_region(str(region_id)):
            raise NotFoundError("Объект не найден")


_service = AuthorizationService()


def get_authorization_service() -> AuthorizationService:
    """Служба авторизации процесса. Не хранит состояния, потому общая."""
    return _service
