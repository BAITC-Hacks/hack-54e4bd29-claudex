"""Композиционный корень.

Единственное место, где бизнес-сервисы соединяются с конкретными
реализациями хранилища. Это позволяет сохранить направление зависимости:
бизнес-слой объявляет порты, слой репозиториев их выполняет, и ни один
из них не знает о другом.

Модуль намеренно вынесен из слоёв: он собирает приложение, а не
участвует в предметной области.
"""

from __future__ import annotations

from app.business.audit.service import AuditService
from app.business.hospitals.service import HospitalService
from app.business.incidents.service import IncidentService
from app.business.ingestion.query import DataImportQueryService
from app.business.ports import UnitOfWorkFactory
from app.business.regions.service import RegionService
from app.business.shared.events import EventDispatcher, get_event_dispatcher
from app.business.signals.service import SignalService
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
