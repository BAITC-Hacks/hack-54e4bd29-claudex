"""Сборка маршрутов версии v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import audit, directory, health, signals, system

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(system.router)
api_router.include_router(directory.router)
api_router.include_router(signals.router)
api_router.include_router(audit.router)
