"""Проверка токенов Keycloak (ADR-0009).

MedSignal не аутентифицирует пользователя и не хранит пароли. Он проверяет
предъявленный токен и строит из него контекст доступа.

Проверяются все четыре свойства: подпись, издатель, аудитория, срок действия.
Пропуск любого из них делает проверку декоративной.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthenticatedError
from app.core.logging import get_logger
from app.security.context import (
    DataScopeResolver,
    NullDataScopeResolver,
    Role,
    SecurityContext,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Разобранные утверждения токена."""

    subject: str
    username: str | None
    email: str | None
    roles: frozenset[Role]
    token_id: str | None


class TokenVerifier(Protocol):
    """Контракт проверки токена.

    Подставной адаптер для тестов реализует этот же протокол,
    поэтому прикладной код не знает, кто именно проверил токен.
    """

    def verify(self, token: str) -> TokenClaims: ...


def _extract_roles(payload: dict[str, Any], claim_path: str) -> frozenset[Role]:
    """Извлечь роли по пути вида `realm_access.roles`."""
    node: Any = payload
    for part in claim_path.split("."):
        if not isinstance(node, dict):
            return frozenset()
        node = node.get(part)

    if not isinstance(node, list | tuple):
        return frozenset()

    parsed = (Role.parse(str(item)) for item in node)
    return frozenset(role for role in parsed if role is not None)


class KeycloakTokenVerifier:
    """Проверка подписанного токена по ключам провайдера."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwk_client = PyJWKClient(
            settings.oidc_jwks_url,
            cache_keys=True,
            lifespan=settings.oidc_jwks_cache_ttl_s,
        )

    def verify(self, token: str) -> TokenClaims:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self._settings.jwt_algorithms),
                audience=self._settings.oidc_audience,
                issuer=self._settings.oidc_issuer,
                leeway=self._settings.oidc_leeway_s,
                options={
                    "require": ["exp", "iat", "iss", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise UnauthenticatedError("Срок действия токена истёк") from exc
        except jwt.InvalidAudienceError as exc:
            raise UnauthenticatedError("Токен предназначен другому получателю") from exc
        except jwt.InvalidIssuerError as exc:
            raise UnauthenticatedError("Токен выпущен неизвестным издателем") from exc
        except jwt.PyJWTError as exc:
            # Причина остаётся в журнале; наружу уходит общее сообщение,
            # чтобы не подсказывать подбирающему форму нужного токена.
            logger.info("Токен отклонён", extra={"reason": type(exc).__name__})
            raise UnauthenticatedError("Токен недействителен") from exc
        except Exception as exc:  # недоступность провайдера ключей
            logger.error("Не удалось проверить токен", exc_info=exc)
            raise UnauthenticatedError("Проверка токена временно невозможна") from exc

        subject = str(payload.get("sub", "")).strip()
        if not subject:
            raise UnauthenticatedError("Токен не содержит идентификатора субъекта")

        return TokenClaims(
            subject=subject,
            username=payload.get("preferred_username"),
            email=payload.get("email"),
            roles=_extract_roles(payload, self._settings.oidc_realm_roles_claim),
            token_id=payload.get("jti"),
        )


class AuthenticationService:
    """Строит контекст доступа из предъявленного токена."""

    def __init__(
        self, verifier: TokenVerifier, scope_resolver: DataScopeResolver
    ) -> None:
        self._verifier = verifier
        self._scope_resolver = scope_resolver

    def authenticate(self, token: str) -> SecurityContext:
        claims = self._verifier.verify(token)
        scope = self._scope_resolver.resolve(claims.subject, claims.roles)
        return SecurityContext(
            user_id=claims.subject,
            username=claims.username,
            email=claims.email,
            roles=claims.roles,
            scope=scope,
            token_id=claims.token_id,
        )


@lru_cache(maxsize=1)
def get_token_verifier() -> TokenVerifier:
    """Проверяющий токен для процесса.

    Кэшируется: клиент ключей провайдера держит их у себя и не должен
    создаваться заново на каждый запрос.

    Подставной адаптер включается только явной настройкой и только
    в локальной среде — за этим следит валидация конфигурации. Запасным
    вариантом при отказе Keycloak он не является никогда.
    """
    settings = get_settings()
    if settings.auth_test_mode:
        from app.security.testing import StaticTokenVerifier

        logger.warning(
            "Включён подставной адаптер аутентификации. "
            "Допустимо только для автоматических тестов."
        )
        return StaticTokenVerifier()
    return KeycloakTokenVerifier(settings)


@lru_cache(maxsize=1)
def get_authentication_service() -> AuthenticationService:
    """Служба аутентификации процесса.

    Подставной адаптер включается только явной настройкой и только
    в локальной среде — за этим следит валидация конфигурации.
    Он никогда не используется как запасной вариант при отказе Keycloak.
    """
    settings = get_settings()
    verifier: TokenVerifier
    if settings.auth_test_mode:
        from app.security.testing import StaticTokenVerifier

        logger.warning(
            "Включён подставной адаптер аутентификации. "
            "Допустимо только для автоматических тестов."
        )
        verifier = StaticTokenVerifier()
    else:
        verifier = KeycloakTokenVerifier(settings)

    return AuthenticationService(verifier, NullDataScopeResolver())
