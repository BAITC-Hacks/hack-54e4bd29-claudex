"""PostgreSQL lineage metadata for forecasting datasets."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import NotFoundError
from app.models.data_import import DataImport
from app.models.delivery import Delivery
from app.models.enums import DataImportStatus, DatasetType
from app.repositories.mapping import SqlAlchemyMappingRepository
from app.shared.forecasting import ReferralDatasetWatermark


class SqlAlchemyForecastMetadataRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _published_referrals(self) -> list[DataImport]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(DataImport)
                .outerjoin(Delivery, DataImport.delivery_id == Delivery.id)
                .where(
                    DataImport.dataset_type == DatasetType.REFERRALS,
                    DataImport.status == DataImportStatus.COMPLETED,
                    or_(DataImport.delivery_id.is_(None), Delivery.status == "PUBLISHED"),
                )
                .order_by(DataImport.completed_at, DataImport.id)
            ).all()
            session.expunge_all()
        return list(rows)

    def referral_history_import_ids(self) -> tuple[UUID, ...]:
        return tuple(item.id for item in self._published_referrals())

    def referral_watermark(self) -> ReferralDatasetWatermark:
        rows = self._published_referrals()
        completed_at = tuple(
            item.completed_at for item in rows if item.completed_at is not None
        )
        if not completed_at:
            raise NotFoundError("Нет завершённого импорта направлений")
        return ReferralDatasetWatermark(
            completed_at=max(completed_at),
            import_ids=tuple(item.id for item in rows),
            file_hashes=tuple(item.file_hash for item in rows),
        )

    def mapping_is_current(self, version: str) -> bool:
        with self._session_factory() as session:
            state = SqlAlchemyMappingRepository(session).readiness()
            return bool(state.verified and state.version == version)

    def current_mapping_version(self) -> str | None:
        with self._session_factory() as session:
            state = SqlAlchemyMappingRepository(session).readiness()
            return state.version if state.verified else None
