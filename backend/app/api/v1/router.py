"""Сборка маршрутов версии v1.

Доменные маршруты — регионы, организации, сигналы, прогнозы, симуляции —
подключаются здесь начиная с PHASE 2.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health, system

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(system.router)
