"""Точка входа приложения FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.error_handlers import register_exception_handlers
from app.core.config import Settings, load_settings_or_exit
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.request_context import REQUEST_ID_HEADER

logger = get_logger(__name__)

APP_DESCRIPTION = """
Система раннего предупреждения о риске перегрузки медицинских организаций.

MedSignal является системой поддержки принятия решений. Прогнозы и сценарии
являются расчётными оценками. Управленческое решение принимает уполномоченный
сотрудник.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger.info(
        "Приложение запускается",
        extra={
            "environment": settings.app_env.value,
            "version": settings.app_version,
            "auth_test_mode": settings.auth_test_mode,
        },
    )
    yield

    # Закрытие пулов при остановке: соединения не должны переживать процесс.
    from app.database import clickhouse, postgres, redis

    postgres.dispose_engine()
    clickhouse.close_client()
    redis.close_clients()
    logger.info("Приложение остановлено")


def create_app() -> FastAPI:
    # Конфигурация проверяется до всего остального. Маршруты импортируются
    # ниже намеренно: они тянут за собой Celery и клиенты хранилищ, которые
    # сами читают настройки. При импорте наверху модуля ошибка конфигурации
    # всплывала бы трассировкой раньше, чем до неё доберётся понятный
    # обработчик, и разработчик не увидел бы, что именно не так.
    settings = load_settings_or_exit()

    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        service=settings.app_name,
        environment=settings.app_env.value,
    )

    from app.api.v1.router import api_router

    app = FastAPI(
        title="MedSignal API",
        description=APP_DESCRIPTION,
        version=settings.app_version,
        lifespan=lifespan,
        # Документация публикуется в рамках префикса API, чтобы обратный
        # прокси мог управлять её доступностью одним правилом.
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=None,
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
    app.state.settings = settings

    _configure_middleware(app, settings)
    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.api_prefix)

    if settings.metrics_enabled:
        _mount_metrics(app, settings)

    return app


def _configure_middleware(app: FastAPI, settings: Settings) -> None:
    # Порядок важен: добавленный последним выполняется первым.
    # Идентификатор запроса должен существовать до всего остального,
    # иначе записи журнала об отказах останутся без него.
    app.add_middleware(SecurityHeadersMiddleware, force_https=settings.force_https)

    if settings.allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts)
        )

    # Явный список источников. Wildcard запрещён вне локальной среды
    # проверкой конфигурации (SECURITY.md, раздел 6.2).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )

    app.add_middleware(RequestContextMiddleware)


def _mount_metrics(app: FastAPI, settings: Settings) -> None:
    """Метрики Prometheus.

    Эндпоинт намеренно вынесен за пределы префикса API: обратный прокси
    маршрутизирует наружу только `/api/`, поэтому метрики недоступны
    из Internet (SECURITY.md, раздел 2).
    """
    from prometheus_client import make_asgi_app

    app.mount(settings.metrics_path, make_asgi_app())


app = create_app()
