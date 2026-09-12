"""Репозитории прогнозов, сценариев и импортов.

На этом этапе это хранение метаданных: модель не обучается, сценарий
не рассчитывается, файл не разбирается. Контракты нужны, чтобы
подключение реальной реализации не меняло схему и слои.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.analytics import Forecast, Scenario
from app.models.data_import import DataImport
from app.models.directory import Hospital
from app.models.enums import DataImportStatus, ForecastStatus
from app.repositories.directory import apply_sort, count_of
from app.repositories.scope import hospital_clause
from app.security.context import DataScope
from app.shared.pagination import PageRequest

SCENARIO_SORT_COLUMNS = {"created_at": Scenario.created_at, "status": Scenario.status}

type ScenarioPage = tuple[list[Scenario], int]


class SqlAlchemyForecastRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _scoped(self, scope: DataScope) -> Select[tuple[Forecast]]:
        return (
            select(Forecast)
            .join(Hospital, Forecast.hospital_id == Hospital.id)
            .where(hospital_clause(scope))
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


class SqlAlchemyScenarioRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _scoped(self, scope: DataScope) -> Select[tuple[Scenario]]:
        return (
            select(Scenario)
            .join(Hospital, Scenario.hospital_id == Hospital.id)
            .where(hospital_clause(scope))
        )

    def get(self, scenario_id: uuid.UUID, scope: DataScope) -> Scenario | None:
        statement = self._scoped(scope).where(Scenario.id == scenario_id)
        return self._session.scalars(statement).unique().first()

    def add(self, scenario: Scenario) -> Scenario:
        self._session.add(scenario)
        self._session.flush()
        return scenario

    def list(self, scope: DataScope, page: PageRequest) -> ScenarioPage:
        statement = self._scoped(scope)
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
