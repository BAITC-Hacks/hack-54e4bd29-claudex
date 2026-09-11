"""Подставной адаптер аутентификации для автоматических тестов (ADR-0009).

Существует, чтобы тесты не требовали работающего Keycloak.

Три ограничения, без которых адаптер превращается в обход аутентификации:

1. Включается только переменной `AUTH_TEST_MODE`, по умолчанию выключен.
2. Приложение отказывается стартовать с ним вне локальной среды —
   за этим следит валидация конфигурации.
3. Никогда не срабатывает как запасной вариант при отказе провайдера.
"""

from __future__ import annotations

import json

from app.core.exceptions import UnauthenticatedError
from app.security.context import Role
from app.security.oidc import TokenClaims

# Формат подставного токена: "test:<base64url-json>" либо простое имя
# из набора заранее описанных субъектов. Подписи нет и быть не должно —
# этот адаптер не притворяется провайдером.
# S105/S106 ниже: это подставные значения тестового адаптера, не секреты.
TEST_TOKEN_PREFIX = "test:"  # noqa: S105

PRESET_SUBJECTS: dict[str, TokenClaims] = {
    "admin": TokenClaims(
        subject="00000000-0000-0000-0000-0000000000a1",
        username="test-admin",
        email=None,
        roles=frozenset({Role.ADMIN}),
        token_id="test-admin",  # noqa: S106
    ),
    "regional-analyst": TokenClaims(
        subject="00000000-0000-0000-0000-0000000000a2",
        username="test-regional-analyst",
        email=None,
        roles=frozenset({Role.REGIONAL_ANALYST}),
        token_id="test-regional-analyst",  # noqa: S106
    ),
    "hospital-manager": TokenClaims(
        subject="00000000-0000-0000-0000-0000000000a3",
        username="test-hospital-manager",
        email=None,
        roles=frozenset({Role.HOSPITAL_MANAGER}),
        token_id="test-hospital-manager",  # noqa: S106
    ),
    "no-roles": TokenClaims(
        subject="00000000-0000-0000-0000-0000000000a4",
        username="test-no-roles",
        email=None,
        roles=frozenset(),
        token_id="test-no-roles",  # noqa: S106
    ),
}


class StaticTokenVerifier:
    """Разбирает подставной токен без обращения к провайдеру."""

    def verify(self, token: str) -> TokenClaims:
        if not token.startswith(TEST_TOKEN_PREFIX):
            raise UnauthenticatedError("Токен недействителен")

        payload = token[len(TEST_TOKEN_PREFIX) :]

        preset = PRESET_SUBJECTS.get(payload)
        if preset is not None:
            return preset

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise UnauthenticatedError("Токен недействителен") from exc

        subject = str(data.get("sub", "")).strip()
        if not subject:
            raise UnauthenticatedError("Токен не содержит идентификатора субъекта")

        parsed = (Role.parse(str(item)) for item in data.get("roles", []))
        return TokenClaims(
            subject=subject,
            username=data.get("preferred_username"),
            email=data.get("email"),
            roles=frozenset(role for role in parsed if role is not None),
            token_id=data.get("jti"),
        )


def make_test_token(subject: str, roles: list[Role] | None = None) -> str:
    """Собрать подставной токен для теста."""
    return TEST_TOKEN_PREFIX + json.dumps(
        {"sub": subject, "roles": [role.value for role in (roles or [])]}
    )
