"""Конфигурация: приложение отказывается стартовать с небезопасными значениями.

Проверяется требование SECURITY.md, раздел 11: молча запустившееся
приложение с заглушкой вместо секрета опаснее не запустившегося.
"""

from __future__ import annotations

import pytest

from app.core.config import LOCAL_ONLY_SECRET_MARKER, AppEnv, Settings

PRODUCTION_BASE = {
    "app_env": "production",
    "app_debug": False,
    "log_level": "INFO",
    "app_secret": "9f2c4b7e1a",
    "cors_allowed_origins": "https://medsignal.example.kz",
    "oidc_issuer": "https://id.example.kz/realms/medsignal",
    "oidc_internal_base_url": "http://keycloak:8080/realms/medsignal",
    "postgres_password": "4a1d9c",
    "clickhouse_password": "7b3e2f",
    "redis_password": "1c8a5d",
    "minio_access_key": "6e4f2b",
    "minio_secret_key": "3d9a7c",
    "auth_test_mode": False,
}


def build(**overrides: object) -> Settings:
    return Settings(**{**PRODUCTION_BASE, **overrides})  # type: ignore[arg-type]


def test_valid_production_configuration_is_accepted() -> None:
    settings = build()
    assert settings.app_env is AppEnv.PRODUCTION


def test_local_environment_allows_example_values() -> None:
    """Локальная разработка работает со значениями из .env.example."""
    settings = Settings(
        app_env="local",
        app_debug=True,
        app_secret=f"dev-{LOCAL_ONLY_SECRET_MARKER}",
        cors_allowed_origins="http://localhost:3000",
    )
    assert settings.app_env.is_local


def test_local_environment_requires_app_secret() -> None:
    with pytest.raises(ValueError, match="APP_SECRET"):
        Settings(app_env="local", app_secret="")


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"app_debug": True}, "APP_DEBUG"),
        ({"log_level": "DEBUG"}, "LOG_LEVEL"),
        ({"auth_test_mode": True}, "AUTH_TEST_MODE"),
        ({"cors_allowed_origins": "*"}, "'*'"),
        ({"cors_allowed_origins": ""}, "CORS_ALLOWED_ORIGINS"),
        ({"oidc_issuer": ""}, "OIDC_ISSUER"),
        ({"oidc_issuer": "http://id.example.kz/realms/m"}, "https"),
        ({"oidc_algorithms": "none"}, "недопустим"),
        ({"oidc_algorithms": "HS256"}, "недопустим"),
        ({"postgres_password": ""}, "POSTGRES_PASSWORD"),
    ],
)
def test_unsafe_production_configuration_is_rejected(
    overrides: dict[str, object], expected: str
) -> None:
    with pytest.raises(ValueError, match=expected):
        build(**overrides)


@pytest.mark.parametrize(
    "field",
    [
        "app_secret",
        "postgres_password",
        "clickhouse_password",
        "redis_password",
        "minio_access_key",
        "minio_secret_key",
    ],
)
def test_example_secrets_are_rejected_outside_local(field: str) -> None:
    """Значение из .env.example не может использоваться вне локальной среды."""
    with pytest.raises(ValueError, match="env.example"):
        build(**{field: f"value-{LOCAL_ONLY_SECRET_MARKER}"})


def test_issuer_and_internal_base_url_are_separate() -> None:
    """Публичный издатель и внутренний адрес ключей различаются (ADR-0009)."""
    settings = build()
    assert settings.oidc_issuer != settings.oidc_internal_base_url
    assert settings.oidc_jwks_url.startswith(settings.oidc_internal_base_url)
    assert settings.oidc_jwks_url.endswith("/protocol/openid-connect/certs")


def test_dsn_uses_configured_values() -> None:
    settings = build(postgres_host="db", postgres_port=5555, postgres_db="ms")
    assert "db:5555/ms" in settings.postgres_dsn


def test_redis_databases_are_separated() -> None:
    """Кэш, брокер и результаты живут в разных базах (ADR-0003)."""
    settings = build()
    urls = {
        settings.redis_cache_url,
        settings.celery_broker_url,
        settings.celery_result_backend,
    }
    assert len(urls) == 3


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        Settings(app_env="local", app_secret="x", log_level="TRACE")
