"""Сборка маршрутов версии v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    audit,
    copilot,
    data_imports,
    directory,
    forecasts,
    health,
    scenarios,
    signals,
    system,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(system.router)
api_router.include_router(directory.router)
api_router.include_router(signals.router)
api_router.include_router(copilot.router)
api_router.include_router(audit.router)
api_router.include_router(data_imports.router)
api_router.include_router(analytics.router)
api_router.include_router(forecasts.router)
api_router.include_router(scenarios.router)
