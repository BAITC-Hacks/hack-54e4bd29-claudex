"""Единица работы поверх сессии SQLAlchemy.

Существует ради одного требования: бизнес-операция и запись аудита
фиксируются одной транзакцией. Журнал, расходящийся с данными, хуже
отсутствующего журнала.

Выход из блока без явной фиксации откатывает транзакцию. Это выбрано
осознанно: забытый commit должен приводить к потере изменения, а не
к его случайной записи.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from app.database.postgres import get_session_factory
from app.repositories.access import SqlAlchemyUserRepository
from app.repositories.analytics import (
    SqlAlchemyDataImportRepository,
    SqlAlchemyForecastRepository,
    SqlAlchemyModelVersionRepository,
    SqlAlchemyScenarioRepository,
)
from app.repositories.audit import SqlAlchemyAuditRepository
from app.repositories.delivery import SqlAlchemyDeliveryRepository
from app.repositories.directory import (
    SqlAlchemyHospitalRepository,
    SqlAlchemyRegionRepository,
)
from app.repositories.incidents import (
    SqlAlchemyActionRepository,
    SqlAlchemyIncidentRepository,
)
from app.repositories.mapping import (
    SqlAlchemyMappingRepository,
    SqlAlchemyOrganizationAliasRepository,
    SqlAlchemyProfileAliasRepository,
    SqlAlchemyRegionAliasRepository,
)
from app.repositories.operations import OperationRepository
from app.repositories.quality import (
    SqlAlchemyDataQualityRepository,
    SqlAlchemyQuarantineRepository,
)
from app.repositories.signals import SqlAlchemySignalRepository


class SqlAlchemyUnitOfWork:
    """Набор репозиториев, работающих в одной транзакции."""

    # Атрибуты объявлены на уровне класса: без этого структурная
    # совместимость с протоколом UnitOfWork не проверяется.
    regions: SqlAlchemyRegionRepository
    hospitals: SqlAlchemyHospitalRepository
    signals: SqlAlchemySignalRepository
    incidents: SqlAlchemyIncidentRepository
    actions: SqlAlchemyActionRepository
    forecasts: SqlAlchemyForecastRepository
    model_versions: SqlAlchemyModelVersionRepository
    scenarios: SqlAlchemyScenarioRepository
    mappings: SqlAlchemyMappingRepository
    deliveries: SqlAlchemyDeliveryRepository
    data_imports: SqlAlchemyDataImportRepository
    data_quality: SqlAlchemyDataQualityRepository
    quarantine: SqlAlchemyQuarantineRepository
    organization_aliases: SqlAlchemyOrganizationAliasRepository
    region_aliases: SqlAlchemyRegionAliasRepository
    profile_aliases: SqlAlchemyProfileAliasRepository
    audit: SqlAlchemyAuditRepository
    users: SqlAlchemyUserRepository
    operations: OperationRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    # ------------------------------------------------------------------
    # Управление транзакцией
    # ------------------------------------------------------------------

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        session = self._session_factory()
        self._session = session
        self._committed = False

        self.regions = SqlAlchemyRegionRepository(session)
        self.hospitals = SqlAlchemyHospitalRepository(session)
        self.signals = SqlAlchemySignalRepository(session)
        self.incidents = SqlAlchemyIncidentRepository(session)
        self.actions = SqlAlchemyActionRepository(session)
        self.forecasts = SqlAlchemyForecastRepository(session)
        self.model_versions = SqlAlchemyModelVersionRepository(session)
        self.scenarios = SqlAlchemyScenarioRepository(session)
        self.mappings = SqlAlchemyMappingRepository(session)
        self.deliveries = SqlAlchemyDeliveryRepository(session)
        self.data_imports = SqlAlchemyDataImportRepository(session)
        self.data_quality = SqlAlchemyDataQualityRepository(session)
        self.quarantine = SqlAlchemyQuarantineRepository(session)
        self.organization_aliases = SqlAlchemyOrganizationAliasRepository(session)
        self.region_aliases = SqlAlchemyRegionAliasRepository(session)
        self.profile_aliases = SqlAlchemyProfileAliasRepository(session)
        self.audit = SqlAlchemyAuditRepository(session)
        self.users = SqlAlchemyUserRepository(session)
        self.operations = OperationRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._session
        if session is None:
            return
        try:
            if exc_type is not None:
                session.rollback()
            elif not self._committed:
                # Успешное чтение: объекты отсоединяются до отката.
                # Откат сбрасывает состояние всех объектов сессии, и
                # прочитанная сущность, отданная наружу, при обращении
                # к любому полю пыталась бы перечитать себя из уже
                # закрытой сессии. Отсоединение сохраняет загруженные
                # значения; незагруженные связи объявлены как lazy="raise"
                # и дают явную ошибку вместо скрытого запроса.
                session.expunge_all()
                session.rollback()
        finally:
            session.close()
            self._session = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Единица работы используется вне блока with")
        return self._session

    def commit(self) -> None:
        self.session.commit()
        self._committed = True

    def rollback(self) -> None:
        self.session.rollback()

    def flush(self) -> None:
        self.session.flush()


def create_unit_of_work() -> SqlAlchemyUnitOfWork:
    """Фабрика единицы работы для композиционного корня."""
    return SqlAlchemyUnitOfWork(get_session_factory())
