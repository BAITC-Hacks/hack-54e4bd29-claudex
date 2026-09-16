"""PostgreSQL lineage metadata for forecasting datasets."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import NotFoundError
from app.models.data_import import DataImport
from app.models.enums import DataImportStatus, DatasetType
from app.shared.forecasting import ReferralDatasetWatermark


class SqlAlchemyForecastMetadataRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def referral_watermark(self) -> ReferralDatasetWatermark:
        with self._session_factory() as session:
            rows = session.scalars(
                select(DataImport)
                .where(
                    DataImport.dataset_type == DatasetType.REFERRALS,
                    DataImport.status == DataImportStatus.COMPLETED,
                )
                .order_by(DataImport.completed_at, DataImport.id)
            ).all()
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
