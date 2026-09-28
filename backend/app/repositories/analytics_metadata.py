"""PostgreSQL metadata used to contextualize ClickHouse aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.data_import import DataImport
from app.models.delivery import Delivery
from app.models.directory import Hospital
from app.models.enums import DataImportStatus
from app.models.quality import DataQualityResult
from app.repositories.delivery import SqlAlchemyDeliveryRepository
from app.repositories.mapping import SqlAlchemyMappingRepository
from app.shared.analytics_data import ImportSummary, ImportWatermark
from app.shared.delivery import DeliveryReadiness


class SqlAlchemyAnalyticsMetadataRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def hospital_ids_for_regions(
        self, region_ids: tuple[uuid.UUID, ...]
    ) -> tuple[uuid.UUID, ...]:
        if not region_ids:
            return ()
        with self._session_factory() as session:
            rows = session.scalars(
                select(Hospital.id)
                .where(Hospital.region_id.in_(region_ids), Hospital.is_active.is_(True))
                .order_by(Hospital.id)
            ).all()
        return tuple(rows)

    def _completed_rows(self) -> list[DataImport]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(DataImport)
                .outerjoin(Delivery, DataImport.delivery_id == Delivery.id)
                .where(
                    DataImport.status == DataImportStatus.COMPLETED,
                    or_(DataImport.delivery_id.is_(None), Delivery.status == "PUBLISHED"),
                )
                .order_by(DataImport.completed_at.desc())
            ).all()
            session.expunge_all()
        return list(rows)

    def _latest_rows(self) -> list[DataImport]:
        rows = self._completed_rows()
        latest: dict[str, DataImport] = {}
        for row in rows:
            latest.setdefault(row.dataset_type, row)
        return list(latest.values())

    def latest_completed_imports(self) -> ImportWatermark:
        rows = self._completed_rows()
        completed = [row.completed_at for row in rows if row.completed_at is not None]
        with self._session_factory() as session:
            mapping = SqlAlchemyMappingRepository(session).readiness()
        return ImportWatermark(
            mapping_version=mapping.version,
            mapping_generation=mapping.generation,
            mapping_verified=mapping.verified,
            completed_at=max(completed) if completed else None,
            import_ids=tuple(sorted((row.id for row in rows), key=str)),
        )

    def _partial_rows(self) -> list[DataImport]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(DataImport)
                .join(Delivery, DataImport.delivery_id == Delivery.id)
                .where(Delivery.status != "PUBLISHED")
                .order_by(DataImport.completed_at.desc())
            ).all()
            session.expunge_all()
        return list(rows)

    def latest_import_summaries(self) -> tuple[ImportSummary, ...]:
        # A logical dataset can be delivered in multiple files.  The newest row
        # supplies the watermark/source metadata, while counts and quality
        # findings must cover every completed part of that dataset.
        partial_rows = self._partial_rows()
        partial_ids = {row.id for row in partial_rows}
        rows = self._completed_rows() + partial_rows
        if not rows:
            return ()
        ids = [row.id for row in rows]
        with self._session_factory() as session:
            quality_rows = session.scalars(
                select(DataQualityResult)
                .where(DataQualityResult.data_import_id.in_(ids))
                .order_by(DataQualityResult.rule_code)
            ).all()
        issues_by_dataset: dict[str, dict[str, int]] = {}
        dataset_by_import = {row.id: row.dataset_type for row in rows}
        for quality in quality_rows:
            dataset = dataset_by_import[quality.data_import_id]
            issues = issues_by_dataset.setdefault(dataset, {})
            issues[quality.rule_code] = (
                issues.get(quality.rule_code, 0) + quality.affected_rows
            )
        summaries: list[ImportSummary] = []
        grouped: dict[str, list[DataImport]] = {}
        for row in rows:
            grouped.setdefault(row.dataset_type, []).append(row)
        for dataset_type, dataset_rows in sorted(grouped.items()):
            latest = max(
                dataset_rows,
                key=lambda row: (
                    row.completed_at is not None,
                    row.completed_at or row.created_at,
                ),
            )
            if latest.completed_at is None:
                continue
            summaries.append(
                ImportSummary(
                    dataset_type=dataset_type,
                    source=latest.source,
                    completeness="PARTIAL"
                    if any(row.id in partial_ids for row in dataset_rows)
                    else "UNKNOWN",
                    import_id=latest.id,
                    completed_at=latest.completed_at,
                    rows_loaded=sum(row.rows_loaded for row in dataset_rows),
                    rows_rejected=sum(row.rows_rejected for row in dataset_rows),
                    warnings_count=sum(row.warnings_count for row in dataset_rows),
                    quality_issues=tuple(
                        f"{code}: {count}"
                        for code, count in sorted(
                            issues_by_dataset.get(dataset_type, {}).items()
                        )
                    ),
                )
            )
        return tuple(summaries)

    def delivery_readiness(self, dataset_type: str) -> DeliveryReadiness:
        with self._session_factory() as session:
            return SqlAlchemyDeliveryRepository(session).readiness(dataset_type)

    def hospital_name(self, hospital_id: uuid.UUID) -> str | None:
        with self._session_factory() as session:
            return session.scalar(select(Hospital.name).where(Hospital.id == hospital_id))

    def hospital_names(self, hospital_ids: tuple[uuid.UUID, ...]) -> dict[uuid.UUID, str]:
        if not hospital_ids:
            return {}
        with self._session_factory() as session:
            rows = session.execute(
                select(Hospital.id, Hospital.name).where(Hospital.id.in_(hospital_ids))
            ).all()
        return {row[0]: row[1] for row in rows}
