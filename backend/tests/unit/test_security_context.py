"""SecurityContext: роли и область данных.

PHASE 1 проверяет абстракцию и правила разрешения. Полноценная доменная
авторизация появляется в PHASE 2 вместе с таблицей областей данных.
"""

from __future__ import annotations

import pytest

from app.security.context import (
    DataScope,
    NullDataScopeResolver,
    Role,
    SecurityContext,
)


def make_context(
    roles: set[Role] | None = None, scope: DataScope | None = None
) -> SecurityContext:
    return SecurityContext(
        user_id="subject-1",
        roles=frozenset(roles or set()),
        scope=scope or DataScope.unresolved(),
    )


@pytest.mark.parametrize(
    "raw",
    ["ADMIN", "admin", " Admin ", "HOSPITAL_MANAGER"],
)
def test_known_roles_are_parsed(raw: str) -> None:
    assert Role.parse(raw) is not None


@pytest.mark.parametrize("raw", ["offline_access", "uma_authorization", "", "unknown"])
def test_unknown_roles_are_ignored(raw: str) -> None:
    """Служебные роли провайдера не должны ломать разбор токена."""
    assert Role.parse(raw) is None


def test_has_role_matches_any_of_listed() -> None:
    context = make_context({Role.REGIONAL_ANALYST})
    assert context.has_role(Role.ADMIN, Role.REGIONAL_ANALYST)
    assert not context.has_role(Role.ADMIN, Role.HOSPITAL_MANAGER)


def test_admin_has_global_scope() -> None:
    assert make_context({Role.ADMIN}).has_global_scope


def test_unresolved_scope_denies_access() -> None:
    """Неразрешённая область трактуется как запрет, а не как разрешение.

    Без этого дефект разрешения области выглядел бы как корректная работа.
    """
    context = make_context({Role.REGIONAL_ANALYST})
    assert not context.scope.resolved
    assert not context.can_access_region("R-1")
    assert not context.can_access_hospital("H-1")


def test_resolved_region_scope_grants_listed_regions_only() -> None:
    context = make_context(
        {Role.REGIONAL_ANALYST},
        DataScope(region_ids=frozenset({"R-1"}), resolved=True),
    )
    assert context.can_access_region("R-1")
    assert not context.can_access_region("R-2")


def test_hospital_is_accessible_through_its_region() -> None:
    context = make_context(
        {Role.REGIONAL_ANALYST},
        DataScope(region_ids=frozenset({"R-1"}), resolved=True),
    )
    assert context.can_access_hospital("H-9", region_id="R-1")
    assert not context.can_access_hospital("H-9", region_id="R-2")


def test_hospital_scope_grants_listed_hospitals_only() -> None:
    context = make_context(
        {Role.HOSPITAL_MANAGER},
        DataScope(hospital_ids=frozenset({"H-1"}), resolved=True),
    )
    assert context.can_access_hospital("H-1")
    assert not context.can_access_hospital("H-2")


def test_global_scope_grants_everything() -> None:
    context = make_context({Role.ADMIN}, DataScope.global_scope())
    assert context.can_access_region("любой")
    assert context.can_access_hospital("любая")


def test_null_resolver_grants_global_scope_to_admin_only() -> None:
    resolver = NullDataScopeResolver()
    assert resolver.resolve("s", frozenset({Role.ADMIN})).is_global
    assert not resolver.resolve("s", frozenset({Role.HOSPITAL_ANALYST})).resolved


def test_context_is_immutable() -> None:
    """Контекст не должен изменяться после разрешения."""
    context = make_context({Role.ADMIN})
    with pytest.raises((AttributeError, TypeError)):
        context.user_id = "другой"  # type: ignore[misc]
