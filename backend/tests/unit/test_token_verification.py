"""Разбор токена и построение контекста доступа (ADR-0009).

Проверка подписи выполняется библиотекой; здесь проверяется то, что
принадлежит MedSignal: извлечение ролей, отображение ошибок провайдера
на контракт приложения, отсутствие запасного пути аутентификации.
"""

from __future__ import annotations

import jwt
import pytest

from app.core.config import Settings
from app.core.exceptions import UnauthenticatedError
from app.security.context import NullDataScopeResolver, Role
from app.security.oidc import (
    AuthenticationService,
    KeycloakTokenVerifier,
    TokenClaims,
    _extract_roles,
)
from app.security.testing import StaticTokenVerifier, make_test_token


def test_roles_are_extracted_from_nested_claim() -> None:
    payload = {"realm_access": {"roles": ["ADMIN", "offline_access"]}}
    assert _extract_roles(payload, "realm_access.roles") == frozenset({Role.ADMIN})


def test_missing_claim_path_yields_no_roles() -> None:
    assert _extract_roles({}, "realm_access.roles") == frozenset()
    assert _extract_roles({"realm_access": {}}, "realm_access.roles") == frozenset()


def test_non_list_claim_yields_no_roles() -> None:
    payload = {"realm_access": {"roles": "ADMIN"}}
    assert _extract_roles(payload, "realm_access.roles") == frozenset()


def test_unknown_roles_do_not_break_extraction() -> None:
    payload = {"realm_access": {"roles": ["uma_authorization", "HOSPITAL_ANALYST"]}}
    assert _extract_roles(payload, "realm_access.roles") == frozenset(
        {Role.HOSPITAL_ANALYST}
    )


class _StubVerifier:
    def __init__(self, claims: TokenClaims) -> None:
        self._claims = claims

    def verify(self, token: str) -> TokenClaims:  # noqa: ARG002
        return self._claims


def test_authentication_builds_context_from_claims() -> None:
    claims = TokenClaims(
        subject="sub-1",
        username="analyst",
        email=None,
        roles=frozenset({Role.REGIONAL_ANALYST}),
        token_id="jti-1",
    )
    context = AuthenticationService(
        _StubVerifier(claims), NullDataScopeResolver()
    ).authenticate("token")

    assert context.user_id == "sub-1"
    assert context.username == "analyst"
    assert context.roles == frozenset({Role.REGIONAL_ANALYST})
    # Область данных разрешается на стороне MedSignal, а не берётся
    # из токена. В PHASE 1 она остаётся неразрешённой.
    assert not context.scope.resolved


def test_admin_receives_global_scope() -> None:
    claims = TokenClaims(
        subject="sub-2",
        username=None,
        email=None,
        roles=frozenset({Role.ADMIN}),
        token_id=None,
    )
    context = AuthenticationService(
        _StubVerifier(claims), NullDataScopeResolver()
    ).authenticate("token")
    assert context.has_global_scope


# --- Подставной адаптер -----------------------------------------------------


def test_test_adapter_accepts_preset_subject() -> None:
    claims = StaticTokenVerifier().verify("test:admin")
    assert Role.ADMIN in claims.roles


def test_test_adapter_accepts_generated_token() -> None:
    token = make_test_token("sub-9", [Role.HOSPITAL_MANAGER])
    claims = StaticTokenVerifier().verify(token)
    assert claims.subject == "sub-9"
    assert claims.roles == frozenset({Role.HOSPITAL_MANAGER})


@pytest.mark.parametrize(
    "token",
    ["", "Bearer abc", "test:", "test:{}", "test:not-json", "eyJhbGciOiJub25lIn0."],
)
def test_test_adapter_rejects_invalid_tokens(token: str) -> None:
    with pytest.raises(UnauthenticatedError):
        StaticTokenVerifier().verify(token)


# --- Настоящий проверяющий --------------------------------------------------


def _verifier() -> KeycloakTokenVerifier:
    settings = Settings(
        app_env="local",
        app_secret="x",
        oidc_issuer="http://localhost/auth/realms/medsignal",
        oidc_internal_base_url="http://keycloak:8080/auth/realms/medsignal",
    )
    return KeycloakTokenVerifier(settings)


def test_unsigned_token_is_rejected() -> None:
    """Токен без подписи не принимается ни при каких обстоятельствах."""
    unsigned = jwt.encode({"sub": "attacker"}, key="", algorithm="none")
    with pytest.raises(UnauthenticatedError):
        _verifier().verify(unsigned)


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(UnauthenticatedError):
        _verifier().verify("совершенно не токен")


def test_provider_failure_does_not_grant_access() -> None:
    """Недоступность провайдера ключей приводит к отказу, а не к пропуску.

    Запасного пути аутентификации не существует (ADR-0009).
    """
    with pytest.raises(UnauthenticatedError):
        _verifier().verify(jwt.encode({"sub": "x"}, key="secret", algorithm="HS256"))
