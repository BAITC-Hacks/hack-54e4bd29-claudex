"""Порты доступа к данным.

Бизнес-слой объявляет, что ему нужно от хранилища; слой репозиториев
это выполняет. Направление зависимости обращено намеренно: правила
не должны знать, чем именно реализовано хранение (ADR-0005).

Протоколы структурные: реализации не импортируют этот модуль, поэтому
правило «репозитории не импортируют бизнес-слой» остаётся в силе.

Область данных передаётся явным параметром каждому запросу. Это
сознательное решение ADR-0006: неявный контекст легко забыть, а забытый
фильтр области — это утечка за границу видимости.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from types import TracebackType
from typing import Any, Protocol

from app.models.access import User
from app.models.action import Action
from app.models.analytics import Forecast, Scenario
from app.models.audit import AuditEvent
from app.models.data_import import DataImport
from app.models.delivery import Delivery
from app.models.directory import Hospital, Region
from app.models.enums import (
    AuditAction,
    AuditEntityType,
    DataImportStatus,
    IncidentStatus,
    SignalClosureDisposition,
    SignalStatus,
)
from app.models.forecast_point import ForecastPoint
from app.models.incident import Incident
from app.models.mapping import OrganizationAlias, ProfileAlias, RegionAlias
from app.models.model_version import ModelVersion
from app.models.quality import DataQualityResult, QuarantineBatch
from app.models.signal import Signal
from app.models.system import SystemOperation
from app.security.context import DataScope
from app.shared.delivery import DeliveryManifest, DeliveryReadiness
from app.shared.filters import (
    AuditFilter,
    HospitalFilter,
    IncidentFilter,
    ScenarioFilter,
    SignalFilter,
)
from app.shared.mapping import MappingReadiness, MappingReviewItem, MappingSnapshot
from app.shared.pagination import PageRequest

# Псевдонимы нужны потому, что внутри протоколов имя `list`
# занято методом: аннотация разрешилась бы в него.
type RegionPage = tuple[list[Region], int]
type HospitalPage = tuple[list[Hospital], int]
type SignalPage = tuple[list[Signal], int]
type SignalList = list[Signal]
type IncidentPage = tuple[list[Incident], int]
type ActionList = list[Action]
type ScenarioPage = tuple[list[Scenario], int]
type AuditPage = tuple[list[AuditEvent], int]
type AuditEventList = list[AuditEvent]
type OperationList = list[SystemOperation]
type DataImportPage = tuple[list[DataImport], int]
type QualityResultList = list[DataQualityResult]
type QuarantineBatchList = list[QuarantineBatch]
type AliasList = list[OrganizationAlias] | list[RegionAlias] | list[ProfileAlias]


class RegionRepository(Protocol):
    def get(self, region_id: uuid.UUID, scope: DataScope) -> Region | None: ...

    def list(self, scope: DataScope, page: PageRequest) -> tuple[list[Region], int]: ...


class HospitalRepository(Protocol):
    def get(self, hospital_id: uuid.UUID, scope: DataScope) -> Hospital | None: ...

    def list(
        self, scope: DataScope, filters: HospitalFilter, page: PageRequest
    ) -> HospitalPage: ...


class SignalRepository(Protocol):
    def get(self, signal_id: uuid.UUID, scope: DataScope) -> Signal | None: ...

    def list(
        self, scope: DataScope, filters: SignalFilter, page: PageRequest
    ) -> SignalPage: ...

    def update_status(
        self,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        new_status: SignalStatus,
        closed_reason: str | None,
        closed_at: datetime | None,
        closure_disposition: SignalClosureDisposition | None,
        now: datetime,
    ) -> Signal | None:
        """Сменить статус при совпадении версии.

        Возвращает None, если версия не совпала: это конфликт одновременного
        изменения, а не отсутствие объекта.
        """
        ...

    def update_assignment(
        self,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        assigned_user_id: uuid.UUID | None,
        now: datetime,
    ) -> Signal | None: ...

    def add_if_absent(self, signal: Signal) -> tuple[Signal, bool]:
        """Atomically insert by dedup key.

        Returns the persisted signal and whether this call created it. The
        implementation must turn a concurrent unique-key race into an
        idempotent replay rather than leaking a storage error.
        """
        ...

    def find_by_dedup_key(self, dedup_key: str) -> Signal | None: ...

    def link_incident(
        self,
        signal_id: uuid.UUID,
        *,
        expected_version: int,
        incident_id: uuid.UUID,
        now: datetime,
    ) -> Signal | None: ...


class IncidentRepository(Protocol):
    def get(self, incident_id: uuid.UUID, scope: DataScope) -> Incident | None: ...

    def list(
        self, scope: DataScope, filters: IncidentFilter, page: PageRequest
    ) -> IncidentPage: ...

    def signals_of(self, incident_id: uuid.UUID, scope: DataScope) -> SignalList: ...

    def add(self, incident: Incident) -> Incident: ...

    def update_assignment(
        self,
        incident_id: uuid.UUID,
        *,
        expected_version: int,
        assigned_user_id: uuid.UUID | None,
        now: datetime,
    ) -> Incident | None: ...

    def update_status(
        self,
        incident_id: uuid.UUID,
        *,
        expected_version: int,
        status: IncidentStatus,
        now: datetime,
    ) -> Incident | None: ...


class ActionRepository(Protocol):
    def add(self, action: Action) -> Action: ...

    def list_for_signal(self, signal_id: uuid.UUID) -> ActionList: ...

    def list_for_incident(self, incident_id: uuid.UUID) -> ActionList: ...


class ForecastRepository(Protocol):
    def get(self, forecast_id: uuid.UUID, scope: DataScope) -> Forecast | None: ...

    def latest_for_hospital(
        self, hospital_id: uuid.UUID, target: str, scope: DataScope
    ) -> Forecast | None: ...

    def add(self, forecast: Forecast) -> Forecast: ...

    def add_points(self, points: Sequence[ForecastPoint]) -> int: ...

    def latest_global(self, target: str) -> Forecast | None: ...

    def points_for(self, forecast_id: uuid.UUID) -> Sequence[ForecastPoint]: ...


class ModelVersionRepository(Protocol):
    def add(self, model_version: ModelVersion) -> ModelVersion: ...


class ScenarioRepository(Protocol):
    def get(self, scenario_id: uuid.UUID, scope: DataScope) -> Scenario | None: ...

    def add_if_absent(self, scenario: Scenario) -> tuple[Scenario, bool]: ...

    def find_by_request(
        self, created_by: uuid.UUID, client_request_id: uuid.UUID
    ) -> Scenario | None: ...

    def list(
        self, scope: DataScope, filters: ScenarioFilter, page: PageRequest
    ) -> tuple[list[Scenario], int]: ...


class DataImportRepository(Protocol):
    def get(self, import_id: uuid.UUID) -> DataImport | None: ...

    def find_by_hash(self, dataset_type: str, file_hash: str) -> DataImport | None: ...

    def add(self, data_import: DataImport) -> DataImport: ...

    def update_status(
        self,
        import_id: uuid.UUID,
        *,
        status: DataImportStatus,
        error_summary: str | None,
        now: datetime,
    ) -> DataImport | None: ...

    def update_statistics(
        self,
        import_id: uuid.UUID,
        *,
        rows_read: int,
        rows_valid: int,
        rows_rejected: int,
        rows_loaded: int,
        warnings_count: int,
        source_size_bytes: int,
        duration_seconds: float,
    ) -> DataImport | None: ...

    def list(
        self, page: PageRequest, dataset_type: str | None = None
    ) -> DataImportPage: ...


class DataQualityRepository(Protocol):
    """Замечания о качестве загрузки. Только добавление и чтение.

    Отчёт описывает конкретную поставку. Переписанный отчёт перестаёт
    описывать то, что тогда произошло, поэтому изменения не предусмотрены.
    """

    def add_many(self, results: Sequence[DataQualityResult]) -> int: ...

    def list_for_import(self, import_id: uuid.UUID) -> QualityResultList: ...


class QuarantineRepository(Protocol):
    """Ссылки на партии, отложенные в карантин."""

    def add_many(self, batches: Sequence[QuarantineBatch]) -> int: ...

    def list_for_import(self, import_id: uuid.UUID) -> QuarantineBatchList: ...


class AliasRepository(Protocol):
    """Сопоставление значений источника со справочником.

    Метода автоматического сопоставления по похожести здесь нет
    намеренно: склейка двух наименований организаций меняет смысл данных
    и требует официального справочника или решения человека.
    """

    def register_many(
        self,
        *,
        source_system: str,
        values: Iterable[tuple[str, str]],
        import_id: uuid.UUID | None,
    ) -> int: ...

    def count_unmapped(self) -> int: ...


class AuditRepository(Protocol):
    """Журнал аудита. Только добавление и чтение.

    Методов изменения и удаления не существует намеренно: смысл журнала
    в неизменности.
    """

    def append(
        self,
        *,
        actor_user_id: uuid.UUID | None,
        action: AuditAction,
        entity_type: AuditEntityType,
        entity_id: uuid.UUID,
        request_id: str | None,
        metadata: dict[str, Any],
    ) -> AuditEvent: ...

    def list(
        self, scope: DataScope, filters: AuditFilter, page: PageRequest
    ) -> AuditPage: ...

    def list_for_entity(
        self, entity_type: AuditEntityType, entity_id: uuid.UUID, *, limit: int
    ) -> AuditEventList:
        """История одного объекта для его карточки."""
        ...


class UserRepository(Protocol):
    def get_by_subject(self, external_subject: str) -> User | None: ...

    def get(self, user_id: uuid.UUID) -> User | None: ...

    def ensure(
        self, *, external_subject: str, display_name: str | None, email: str | None
    ) -> User:
        """Создать проекцию пользователя, если её ещё нет.

        Создание проекции не выдаёт никаких прав: область данных
        назначается администратором отдельно.
        """
        ...

    def resolve_scope(self, user: User) -> DataScope: ...


class SystemOperationRepository(Protocol):
    """Состояние технических и долгих операций (ADR-0010)."""

    def create(
        self, *, operation_type: str, request_id: str | None, created_at: datetime
    ) -> SystemOperation: ...

    def get(self, operation_id: uuid.UUID) -> SystemOperation | None: ...

    def list_recent(self, *, limit: int) -> OperationList: ...

    def mark_running(
        self, operation_id: uuid.UUID, *, celery_task_id: str | None, at: datetime
    ) -> SystemOperation | None: ...

    def mark_completed(
        self, operation_id: uuid.UUID, *, result: dict[str, Any] | None, at: datetime
    ) -> SystemOperation | None: ...

    def mark_failed(
        self, operation_id: uuid.UUID, *, error_summary: str, at: datetime
    ) -> SystemOperation | None: ...


class DeliveryRepository(Protocol):
    def get_by_id(self, delivery_id: uuid.UUID) -> Delivery | None: ...
    def has_complete_parts(self, delivery: Delivery) -> bool: ...

    def lock_source(self, source: str, dataset: str) -> None: ...
    def get(self, delivery_id: str) -> Delivery | None: ...
    def require(self, delivery_id: str, refresh: bool = False) -> Delivery: ...
    def has_legacy(self, source: str, dataset: str) -> bool: ...
    def overlaps(self, manifest: DeliveryManifest) -> bool: ...
    def add_approved(
        self,
        manifest: DeliveryManifest,
        *,
        evidence_ref: str,
        actor: str,
        cadence_days: int | None,
    ) -> Delivery: ...
    def imports(self, delivery_id: uuid.UUID) -> list[DataImport]: ...
    def readiness(
        self, dataset_type: str, source_system: str | None = None
    ) -> DeliveryReadiness: ...


class MappingRepository(Protocol):
    def lock(self) -> None: ...
    def readiness(self) -> MappingReadiness: ...
    def review(
        self, *, kind: str, status: str | None, limit: int
    ) -> tuple[list[MappingReviewItem], int]: ...
    def get_alias(
        self, alias_id: uuid.UUID, kind: str = "ORGANIZATION"
    ) -> OrganizationAlias | RegionAlias | None: ...
    def target_exists(self, target_id: uuid.UUID, kind: str) -> bool: ...
    def register(
        self, *, kind: str, source_system: str, identity_space: str, source_key: str
    ) -> OrganizationAlias | RegionAlias: ...
    def record_decision(self, *, actor: str, evidence_ref: str) -> str: ...
    def candidate(self, version: str) -> MappingSnapshot: ...
    def activate(self, version: str) -> None: ...


class UnitOfWork(Protocol):
    """Единица работы: общая транзакция для набора репозиториев.

    Нужна требованию атомарности: бизнес-операция и запись аудита
    фиксируются вместе. Журнал, расходящийся с данными, хуже
    отсутствующего журнала.
    """

    # Объявлены свойствами, а не полями: изменяемое поле протокола
    # требует точного совпадения типа, и конкретная реализация
    # с собственными классами репозиториев его не удовлетворяла бы.
    @property
    def regions(self) -> RegionRepository: ...

    @property
    def hospitals(self) -> HospitalRepository: ...

    @property
    def signals(self) -> SignalRepository: ...

    @property
    def incidents(self) -> IncidentRepository: ...

    @property
    def actions(self) -> ActionRepository: ...

    @property
    def forecasts(self) -> ForecastRepository: ...

    @property
    def model_versions(self) -> ModelVersionRepository: ...

    @property
    def scenarios(self) -> ScenarioRepository: ...

    @property
    def data_imports(self) -> DataImportRepository: ...

    @property
    def deliveries(self) -> DeliveryRepository: ...

    @property
    def mappings(self) -> MappingRepository: ...

    @property
    def data_quality(self) -> DataQualityRepository: ...

    @property
    def quarantine(self) -> QuarantineRepository: ...

    @property
    def organization_aliases(self) -> AliasRepository: ...

    @property
    def region_aliases(self) -> AliasRepository: ...

    @property
    def profile_aliases(self) -> AliasRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def users(self) -> UserRepository: ...

    @property
    def operations(self) -> SystemOperationRepository: ...

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def flush(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
