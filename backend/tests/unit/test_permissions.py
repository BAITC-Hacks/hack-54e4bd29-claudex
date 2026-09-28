"""Матрица прав и разделение ответственности ролей."""

from __future__ import annotations

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role
from app.security.permissions import Permission, permissions_for
from tests.fakes import make_context

authz = AuthorizationService()


def test_admin_has_every_permission() -> None:
    assert permissions_for(frozenset({Role.ADMIN})) == frozenset(Permission)


def test_user_without_known_roles_gets_nothing() -> None:
    """Отсутствие роли означает запрет, а не разрешение по умолчанию."""
    assert permissions_for(frozenset()) == frozenset()


@pytest.mark.parametrize(
    "role",
    [
        Role.HEALTH_AUTHORITY,
        Role.REGIONAL_ANALYST,
        Role.HOSPITAL_MANAGER,
        Role.HOSPITAL_ANALYST,
    ],
)
def test_every_role_may_read_signals(role: Role) -> None:
    assert Permission.SIGNAL_READ in permissions_for(frozenset({role}))


def test_hospital_analyst_cannot_decide() -> None:
    """Аналитик исследует и объясняет, решение фиксирует руководитель.

    Это не оформление интерфейса, а разделение ответственности:
    оно должно держаться правами, а не инструкцией.
    """
    granted = permissions_for(frozenset({Role.HOSPITAL_ANALYST}))
    assert Permission.SIGNAL_UPDATE_STATUS not in granted
    assert Permission.SIGNAL_ASSIGN not in granted
    assert Permission.INCIDENT_MANAGE not in granted


def test_hospital_roles_cannot_read_regions() -> None:
    granted = permissions_for(frozenset({Role.HOSPITAL_MANAGER}))
    assert Permission.REGION_READ not in granted


def test_only_admin_and_authority_may_import_data() -> None:
    for role in (Role.REGIONAL_ANALYST, Role.HOSPITAL_MANAGER, Role.HOSPITAL_ANALYST):
        assert Permission.DATA_IMPORT_CREATE not in permissions_for(frozenset({role}))
    assert Permission.DATA_IMPORT_CREATE in permissions_for(
        frozenset({Role.HEALTH_AUTHORITY})
    )


def test_only_admin_manages_users() -> None:
    for role in Role:
        granted = permissions_for(frozenset({role}))
        assert (Permission.ADMIN_MANAGE in granted) is (role is Role.ADMIN)


def test_require_permission_raises_forbidden() -> None:
    context = make_context(roles={Role.HOSPITAL_ANALYST})
    with pytest.raises(ForbiddenError) as error:
        authz.require_permission(context, Permission.SIGNAL_UPDATE_STATUS)
    assert error.value.details["required_permission"] == "signal.update_status"


def test_scope_violation_raises_not_found_not_forbidden() -> None:
    """Объект вне области данных неотличим от отсутствующего.

    Ответ 403 подтверждал бы существование объекта и позволял бы
    перебором выяснить состав организаций региона.
    """
    import uuid

    context = make_context(roles={Role.HOSPITAL_MANAGER}, scope=DataScope.unresolved())
    with pytest.raises(NotFoundError):
        authz.require_hospital_access(context, uuid.uuid4())
