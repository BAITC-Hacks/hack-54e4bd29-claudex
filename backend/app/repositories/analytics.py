"""Репозитории прогнозов, сценариев и импортов.

На этом этапе это хранение метаданных: модель не обучается, сценарий
не рассчитывается, файл не разбирается. Контракты нужны, чтобы
подключение реальной реализации не меняло схему и слои.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.analytics import Forecast, Scenario
from app.models.data_import import DataImport
from app.models.directory import Hospital
from app.models.enums import DataImportStatus, ForecastStatus
from app.models.forecast_point import ForecastPoint
from app.models.model_version import ModelVersion
from app.repositories.directory import apply_sort, count_of
from app.repositories.scope import scoped_entity_clause
from app.security.context import DataScope
from app.shared.filters import ScenarioFilter
from app.shared.pagination import PageRequest

SCENARIO_SORT_COLUMNS = {"created_at": Scenario.created_at}

type ScenarioPage = tuple[list[Scenario], int]


class SqlAlchemyForecastRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _scoped(self, scope: DataScope) -> Select[tuple[Forecast]]:
        return (
            select(Forecast)
            .outerjoin(Hospital, Forecast.hospital_id == Hospital.id)
            .where(
                scoped_entity_clause(
                    scope,
                    scope_type=Forecast.scope_type,
                    region_id=Forecast.region_id,
                    hospital_id=Forecast.hospital_id,
                )
            )
        )

    def get(self, forecast_id: uuid.UUID, scope: DataScope) -> Forecast | None:
        statement = self._scoped(scope).where(Forecast.id == forecast_id)
        return self._session.scalars(statement).unique().first()

    def latest_for_hospital(
        self, hospital_id: uuid.UUID, target: str, scope: DataScope
    ) -> Forecast | None:
        """Последний пригодный прогноз организации.

        Непригодные прогнозы не удаляются, но и не выдаются как
        актуальные: они сохраняются с причиной (ML_ARCHITECTURE.md).
        """
        statement = (
            self._scoped(scope)
            .where(
                Forecast.hospital_id == hospital_id,
                Forecast.target == target,
                Forecast.status == ForecastStatus.VALID,
            )
            .order_by(Forecast.generated_at.desc())
            .limit(1)
        )
        return self._session.scalars(statement).unique().first()

    def add(self, forecast: Forecast) -> Forecast:
        self._session.add(forecast)
        self._session.flush()
        return forecast

    def add_points(self, points: list[ForecastPoint] | tuple[ForecastPoint, ...]) -> int:
        self._session.add_all(points)
        self._session.flush()
        return len(points)

    def latest_global(self, target: str) -> Forecast | None:
        statement = (
            select(Forecast)
            .where(
                Forecast.scope_type == "GLOBAL",
                Forecast.target == target,
                Forecast.status == ForecastStatus.VALID,
            )
            .order_by(Forecast.generated_at.desc(), Forecast.id.desc())
            .limit(1)
        )
        return self._session.scalars(statement).first()

    def points_for(self, forecast_id: uuid.UUID) -> list[ForecastPoint]:
        return list(
            self._session.scalars(
                select(ForecastPoint)
                .where(ForecastPoint.forecast_id == forecast_id)
                .order_by(ForecastPoint.forecast_date)
            ).all()
        )


class SqlAlchemyModelVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, model_version: ModelVersion) -> ModelVersion:
        self._session.add(model_version)
        self._session.flush()
        return model_version


class SqlAlchemyScenarioRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _scoped(self, scope: DataScope) -> Select[tuple[Scenario]]:
        return (
            select(Scenario)
            .outerjoin(Hospital, Scenario.hospital_id == Hospital.id)
            .where(
                scoped_entity_clause(
                    scope,
                    scope_type=Scenario.scope_type,
                    region_id=Scenario.region_id,
                    hospital_id=Scenario.hospital_id,
                )
            )
        )

    def get(self, scenario_id: uuid.UUID, scope: DataScope) -> Scenario | None:
        statement = self._scoped(scope).where(Scenario.id == scenario_id)
        return self._session.scalars(statement).unique().first()

    def add_if_absent(self, scenario: Scenario) -> tuple[Scenario, bool]:
        try:
            with self._session.begin_nested():
                self._session.add(scenario)
                self._session.flush()
        except IntegrityError:
            existing = self.find_by_request(
                scenario.created_by, scenario.client_request_id
            )
            if existing is None:
                raise
            return existing, False
        return scenario, True

    def find_by_request(
        self, created_by: uuid.UUID, client_request_id: uuid.UUID
    ) -> Scenario | None:
        return self._session.scalar(
            select(Scenario).where(
                Scenario.created_by == created_by,
                Scenario.client_request_id == client_request_id,
            )
        )

    def list(
        self, scope: DataScope, filters: ScenarioFilter, page: PageRequest
    ) -> ScenarioPage:
        statement = self._scoped(scope)
        if filters.mapping_version is not None:
            statement = statement.where(
                Scenario.data_watermark["mapping_version"].as_string()
                == filters.mapping_version
            )
        if filters.scenario_type is not None:
            statement = statement.where(Scenario.scenario_type == filters.scenario_type)
        if filters.scope_type is not None:
            statement = statement.where(Scenario.scope_type == filters.scope_type)
        if filters.source_signal_id is not None:
            statement = statement.where(
                Scenario.source_signal_id == filters.source_signal_id
            )
        if filters.source_incident_id is not None:
            statement = statement.where(
                Scenario.source_incident_id == filters.source_incident_id
            )
        total = count_of(self._session, statement)
        statement = apply_sort(statement, page, SCENARIO_SORT_COLUMNS)
        rows = (
            self._session.scalars(statement.offset(page.offset).limit(page.limit))
            .unique()
            .all()
        )
        return list(rows), total


class SqlAlchemyDataImportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, import_id: uuid.UUID) -> DataImport | None:
        return self._session.get(DataImport, import_id)

    def find_by_hash(self, dataset_type: str, file_hash: str) -> DataImport | None:
        """Найти ранее загруженный файл с тем же содержимым.

        Ключ идемпотентности — тип набора и контрольная сумма содержимого.
        Имя файла в него не входит: переименование не делает файл новым.
        """
        statement = select(DataImport).where(
            DataImport.dataset_type == dataset_type,
            DataImport.file_hash == file_hash,
        )
        return self._session.scalars(statement).first()

    def add(self, data_import: DataImport) -> DataImport:
        self._session.add(data_import)
        self._session.flush()
        return data_import

    def update_status(
        self,
        import_id: uuid.UUID,
        *,
        status: DataImportStatus,
        error_summary: str | None,
        now: datetime,
    ) -> DataImport | None:
        data_import = self._session.get(DataImport, import_id)
        if data_import is None:
            return None

        data_import.status = status
        if status is DataImportStatus.RUNNING:
            data_import.started_at = now
        if status.is_terminal:
            data_import.completed_at = now
        if error_summary is not None:
            data_import.error_summary = error_summary

        self._session.flush()
        return data_import

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
    ) -> DataImport | None:
        """Записать итоговые счётчики импорта.

        Счётчики хранятся вместе с записью об импорте, а не вычисляются
        запросом к аналитическому хранилищу: расхождение между источником
        и витриной нужно уметь объяснить и после того, как партиция будет
        удалена политикой хранения.
        """
        data_import = self._session.get(DataImport, import_id)
        if data_import is None:
            return None

        data_import.rows_read = rows_read
        data_import.rows_valid = rows_valid
        data_import.rows_rejected = rows_rejected
        data_import.rows_loaded = rows_loaded
        data_import.warnings_count = warnings_count
        data_import.source_size_bytes = source_size_bytes
        data_import.duration_seconds = duration_seconds

        self._session.flush()
        return data_import

    def list(
        self, page: PageRequest, dataset_type: str | None = None
    ) -> tuple[list[DataImport], int]:
        """Страница импортов, новые сверху.

        Области данных здесь нет намеренно: импорт — операция уровня
        системы, и доступ к нему ограничен правом, а не территорией.
        """
        statement = select(DataImport)
        if dataset_type is not None:
            statement = statement.where(DataImport.dataset_type == dataset_type)

        total = count_of(self._session, statement)
        ordered = (
            statement.order_by(DataImport.created_at.desc())
            .limit(page.page_size)
            .offset(page.offset)
        )
        return list(self._session.scalars(ordered).all()), total
