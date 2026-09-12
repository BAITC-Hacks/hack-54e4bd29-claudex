"""Права на операции и их сопоставление ролям.

Бизнес-код проверяет право, а не роль. Причина прямая: условие вида
`if role == REGIONAL_ANALYST` разбросанное по проекту делает изменение
ролевой модели правкой во многих местах и почти гарантирует расхождение
между кодом и документированной матрицей.

Роли приходят от провайдера идентификации, права — внутреннее понятие
MedSignal. Сопоставление задано здесь и только здесь.
"""

from __future__ import annotations

from enum import StrEnum

from app.security.context import Role


class Permission(StrEnum):
    """Право на выполнение операции."""

    REGION_READ = "region.read"
    HOSPITAL_READ = "hospital.read"

    SIGNAL_READ = "signal.read"
    SIGNAL_UPDATE_STATUS = "signal.update_status"
    SIGNAL_ASSIGN = "signal.assign"

    INCIDENT_READ = "incident.read"
    INCIDENT_MANAGE = "incident.manage"

    ACTION_CREATE = "action.create"

    FORECAST_READ = "forecast.read"

    SCENARIO_READ = "scenario.read"
    SCENARIO_CREATE = "scenario.create"

    DATA_IMPORT_CREATE = "data_import.create"
    DATA_IMPORT_READ = "data_import.read"

    AUDIT_READ = "audit.read"

    ADMIN_MANAGE = "admin.manage"


# Права, доступные всем ролям системы: наблюдение за ситуацией.
_OBSERVER: frozenset[Permission] = frozenset(
    {
        Permission.HOSPITAL_READ,
        Permission.SIGNAL_READ,
        Permission.INCIDENT_READ,
        Permission.FORECAST_READ,
        Permission.SCENARIO_READ,
        Permission.SCENARIO_CREATE,
    }
)

# Права на управленческое решение. Аналитик их не имеет: он исследует
# и объясняет, решение фиксирует руководитель (SECURITY.md, раздел 5).
_DECISION_MAKER: frozenset[Permission] = frozenset(
    {
        Permission.SIGNAL_UPDATE_STATUS,
        Permission.SIGNAL_ASSIGN,
        Permission.INCIDENT_MANAGE,
        Permission.ACTION_CREATE,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.HEALTH_AUTHORITY: _OBSERVER
    | _DECISION_MAKER
    | frozenset(
        {
            Permission.REGION_READ,
            Permission.AUDIT_READ,
            Permission.DATA_IMPORT_CREATE,
            Permission.DATA_IMPORT_READ,
        }
    ),
    Role.REGIONAL_ANALYST: _OBSERVER
    | _DECISION_MAKER
    | frozenset({Permission.REGION_READ, Permission.AUDIT_READ}),
    Role.HOSPITAL_MANAGER: _OBSERVER
    | _DECISION_MAKER
    | frozenset({Permission.AUDIT_READ}),
    # Аналитик организации: только наблюдение и проверка сценариев.
    Role.HOSPITAL_ANALYST: _OBSERVER,
}


def permissions_for(roles: frozenset[Role]) -> frozenset[Permission]:
    """Объединение прав всех ролей пользователя.

    Пользователь без известных системе ролей прав не получает:
    отсутствие роли означает запрет, а не разрешение по умолчанию.
    """
    granted: set[Permission] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)
