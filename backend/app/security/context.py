"""SecurityContext — контекст доступа пользователя.

Контекст разрешается один раз при аутентификации и передаётся вниз
по слоям. Область данных применяется в бизнес-слое явным параметром,
а не в контроллере и не неявно в репозитории (ADR-0006).

PHASE 1 создаёт абстракцию и разрешение ролей. Полноценная доменная
авторизация с таблицей областей данных — PHASE 2.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class Role(StrEnum):
    """Роли системы. Соответствуют ролям области Keycloak."""

    ADMIN = "ADMIN"
    HEALTH_AUTHORITY = "HEALTH_AUTHORITY"
    REGIONAL_ANALYST = "REGIONAL_ANALYST"
    HOSPITAL_MANAGER = "HOSPITAL_MANAGER"
    HOSPITAL_ANALYST = "HOSPITAL_ANALYST"

    @classmethod
    def parse(cls, raw: str) -> Role | None:
        """Роль из claim'а токена. Неизвестные роли игнорируются.

        Провайдер может выдавать собственные служебные роли
        (`offline_access`, `uma_authorization`) — они не являются
        ролями MedSignal и не должны приводить к ошибке.
        """
        try:
            return cls(raw.strip().upper())
        except ValueError:
            return None


# Роли, область данных которых охватывает всю систему.
GLOBAL_SCOPE_ROLES: frozenset[Role] = frozenset({Role.ADMIN})

# Роли, область данных которых задаётся регионами.
REGION_SCOPED_ROLES: frozenset[Role] = frozenset(
    {Role.HEALTH_AUTHORITY, Role.REGIONAL_ANALYST}
)

# Роли, область данных которых задаётся организациями.
HOSPITAL_SCOPED_ROLES: frozenset[Role] = frozenset(
    {Role.HOSPITAL_MANAGER, Role.HOSPITAL_ANALYST}
)


@dataclass(frozen=True, slots=True)
class DataScope:
    """Область данных пользователя.

    `resolved` отличает «область пуста» от «область ещё не разрешена».
    Без этого различия пустая область выглядела бы как корректный запрет
    доступа ко всему, и дефект разрешения области остался бы незамеченным.
    """

    region_ids: frozenset[str] = field(default_factory=frozenset)
    hospital_ids: frozenset[str] = field(default_factory=frozenset)
    is_global: bool = False
    resolved: bool = False

    @classmethod
    def global_scope(cls) -> DataScope:
        return cls(is_global=True, resolved=True)

    @classmethod
    def unresolved(cls) -> DataScope:
        return cls()


@dataclass(frozen=True, slots=True)
class SecurityContext:
    """Кто выполняет запрос и что ему доступно."""

    user_id: str
    roles: frozenset[Role]
    scope: DataScope
    username: str | None = None
    email: str | None = None
    token_id: str | None = None
    # Идентификатор строки пользователя в MedSignal. Нужен внешним ключам
    # назначения и авторства: `user_id` — это субъект провайдера, а не
    # первичный ключ нашей таблицы.
    internal_user_id: uuid.UUID | None = None

    @property
    def actor_id(self) -> uuid.UUID:
        """Автор действия. Отсутствие проекции пользователя — дефект."""
        if self.internal_user_id is None:
            raise RuntimeError(
                "Контекст не содержит внутреннего идентификатора пользователя"
            )
        return self.internal_user_id

    # ------------------------------------------------------------------
    # Права
    # ------------------------------------------------------------------

    def has_role(self, *roles: Role) -> bool:
        return bool(self.roles.intersection(roles))

    @property
    def has_global_scope(self) -> bool:
        return self.scope.is_global or bool(self.roles & GLOBAL_SCOPE_ROLES)

    # ------------------------------------------------------------------
    # Область данных
    # ------------------------------------------------------------------

    def can_access_region(self, region_id: str) -> bool:
        """Доступен ли регион.

        Неразрешённая область не даёт доступа: отсутствие данных об области
        трактуется как запрет, а не как разрешение.
        """
        if self.has_global_scope:
            return True
        if not self.scope.resolved:
            return False
        return region_id in self.scope.region_ids

    def can_access_hospital(self, hospital_id: str, region_id: str | None = None) -> bool:
        """Доступна ли организация.

        Организация доступна напрямую либо через регион, если он известен
        вызывающей стороне.
        """
        if self.has_global_scope:
            return True
        if not self.scope.resolved:
            return False
        if hospital_id in self.scope.hospital_ids:
            return True
        return region_id is not None and region_id in self.scope.region_ids


class DataScopeResolver(Protocol):
    """Разрешение области данных пользователя.

    Область берётся из хранилища MedSignal, а не из токена: изменение,
    внесённое администратором, должно действовать немедленно (ADR-0009).
    """

    def resolve(self, user_id: str, roles: frozenset[Role]) -> DataScope: ...


class NullDataScopeResolver:
    """Реализация PHASE 1.

    Глобальным ролям выдаётся полная область; остальным — неразрешённая.
    Таблица `user_data_scopes` появляется в PHASE 2, вместе с ней
    появится и полноценная реализация.
    """

    def resolve(self, user_id: str, roles: frozenset[Role]) -> DataScope:  # noqa: ARG002
        if roles & GLOBAL_SCOPE_ROLES:
            return DataScope.global_scope()
        return DataScope.unresolved()
