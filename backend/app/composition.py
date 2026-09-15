"""Композиционный корень.

Единственное место, где бизнес-сервисы соединяются с конкретными
реализациями хранилища. Это позволяет сохранить направление зависимости:
бизнес-слой объявляет порты, слой репозиториев их выполняет, и ни один
из них не знает о другом.

Модуль намеренно вынесен из слоёв: он собирает приложение, а не
участвует в предметной области.
"""

from __future__ import annotations

from typing import cast

from app.adapters.analytics_cache import RedisAnalyticsCache, RedisLike
from app.business.analytics.service import AnalyticsService
from app.business.audit.service import AuditService
from app.business.hospitals.service import HospitalService
from app.business.incidents.service import IncidentService
from app.business.ingestion.query import DataImportQueryService
from app.business.ports import UnitOfWorkFactory
from app.business.regions.service import RegionService
from app.business.shared.events import EventDispatcher, get_event_dispatcher
from app.business.signals.service import SignalService
from app.core.config import get_settings
from app.database.clickhouse import get_client as get_clickhouse_client
from app.database.postgres import get_session_factory
from app.database.redis import get_cache_client
from app.repositories.analytics_metadata import SqlAlchemyAnalyticsMetadataRepository
from app.repositories.clickhouse_analytics import (
    ClickHouseAnalyticsRepository,
    ClickHouseQueryClient,
)
from app.repositories.unit_of_work import create_unit_of_work
from app.security.authorization import AuthorizationService, get_authorization_service


def get_unit_of_work_factory() -> UnitOfWorkFactory:
    return create_unit_of_work


def _dependencies() -> tuple[UnitOfWorkFactory, AuthorizationService, EventDispatcher]:
    return (
        get_unit_of_work_factory(),
        get_authorization_service(),
        get_event_dispatcher(),
    )


def build_region_service() -> RegionService:
    uow, authz, _ = _dependencies()
    return RegionService(uow, authz)


def build_hospital_service() -> HospitalService:
    uow, authz, _ = _dependencies()
    return HospitalService(uow, authz)


def build_signal_service() -> SignalService:
    uow, authz, dispatcher = _dependencies()
    return SignalService(uow, authz, dispatcher)


def build_incident_service() -> IncidentService:
    uow, authz, _ = _dependencies()
    return IncidentService(uow, authz)


def build_audit_service() -> AuditService:
    uow, authz, _ = _dependencies()
    return AuditService(uow, authz)


def build_data_import_query_service() -> DataImportQueryService:
    """Чтение истории загрузок.

    Запуск импорта собирается отдельно, в `app.adapters.composition`:
    он требует библиотеки разбора файлов, которой в образе API нет
    и быть не должно.
    """
    uow, authz, _ = _dependencies()
    return DataImportQueryService(uow, authz)


def build_analytics_service() -> AnalyticsService:
    settings = get_settings()
    return AnalyticsService(
        repository=ClickHouseAnalyticsRepository(
            cast(ClickHouseQueryClient, get_clickhouse_client())
        ),
        metadata_repository=SqlAlchemyAnalyticsMetadataRepository(get_session_factory()),
        cache=RedisAnalyticsCache(cast(RedisLike, get_cache_client())),
        authorization=get_authorization_service(),
        min_cell_size=settings.analytics_min_cell_size,
        cache_ttl_seconds=settings.analytics_cache_ttl_seconds,
        max_date_range_days=settings.analytics_max_date_range_days,
    )
