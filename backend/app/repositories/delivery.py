"""Source-serialized reservations. Every reservation blocks competing overlap."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.data_import import DataImport
from app.models.delivery import Delivery, DeliveryPart
from app.shared.delivery import DeliveryManifest, DeliveryMode, DeliveryReadiness


class SqlAlchemyDeliveryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_source(self, source: str, dataset: str) -> None:
        key = int.from_bytes(
            sha256(f"delivery:{source}:{dataset}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        self._session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    def get(self, delivery_id: str) -> Delivery | None:
        return self._session.scalar(
            select(Delivery).where(Delivery.delivery_id == delivery_id)
        )

    def get_by_id(self, delivery_id: UUID) -> Delivery | None:
        return self._session.get(Delivery, delivery_id, populate_existing=True)

    def has_complete_parts(self, delivery: Delivery) -> bool:
        """A publication flag cannot certify only a surviving subset of parts."""
        try:
            manifest = DeliveryManifest.from_payload(delivery.manifest)
        except (ValueError, TypeError, KeyError):
            return False
        expected = tuple(manifest.file_hashes)
        registered = tuple(
            self._session.scalars(
                select(DeliveryPart.file_hash).where(
                    DeliveryPart.delivery_id == delivery.id
                )
            )
        )
        imports = self.imports(delivery.id)
        return bool(
            delivery.approved_at
            and delivery.manifest_digest == manifest.digest
            and delivery.mode == manifest.mode
            and delivery.snapshot_date == manifest.snapshot_date
            and delivery.period_start == manifest.period_start
            and delivery.period_end == manifest.period_end
            and delivery.confirmed_complete_through == manifest.confirmed_complete_through
            and expected
            and len(expected) == len(set(expected))
            and sorted(registered) == sorted(expected)
            and sorted(i.file_hash for i in imports) == sorted(expected)
            and manifest.expected_rows is not None
            and sum(i.rows_read for i in imports) == manifest.expected_rows
            and all(
                i.status == "COMPLETED"
                and i.dataset_type == delivery.dataset_type
                and i.source == delivery.source_system
                and i.rows_rejected == 0
                and i.rows_read == i.rows_valid == i.rows_loaded
                for i in imports
            )
        )

    def require(self, delivery_id: str, refresh: bool = False) -> Delivery:
        stmt = select(Delivery).where(Delivery.delivery_id == delivery_id)
        if refresh:
            stmt = stmt.execution_options(populate_existing=True).with_for_update()
        row = self._session.scalar(stmt)
        if row is None:
            raise NotFoundError("DELIVERY_NOT_REGISTERED")
        return row

    def has_legacy(self, source: str, dataset: str) -> bool:
        return (
            self._session.scalar(
                select(DataImport.id)
                .where(
                    DataImport.source == source,
                    DataImport.dataset_type == dataset,
                    DataImport.delivery_id.is_(None),
                    DataImport.status == "COMPLETED",
                )
                .limit(1)
            )
            is not None
        )

    def overlaps(self, manifest: DeliveryManifest) -> bool:
        stmt = select(Delivery.id).where(
            Delivery.source_system == manifest.source_system,
            Delivery.dataset_type == manifest.dataset_type,
            Delivery.delivery_id != manifest.delivery_id,
        )
        if manifest.mode == DeliveryMode.SNAPSHOT:
            if manifest.snapshot_date is None:
                return True
            stmt = stmt.where(
                or_(
                    Delivery.snapshot_date == manifest.snapshot_date,
                    (Delivery.period_start <= manifest.snapshot_date)
                    & (Delivery.period_end >= manifest.snapshot_date),
                )
            )
        else:
            if manifest.period_start is None or manifest.period_end is None:
                return True
            stmt = stmt.where(
                or_(
                    (Delivery.period_start <= manifest.period_end)
                    & (Delivery.period_end >= manifest.period_start),
                    Delivery.snapshot_date.between(
                        manifest.period_start, manifest.period_end
                    ),
                )
            )
        return self._session.scalar(stmt.limit(1)) is not None

    def add_approved(
        self,
        manifest: DeliveryManifest,
        *,
        evidence_ref: str,
        actor: str,
        cadence_days: int | None,
    ) -> Delivery:
        row = Delivery(
            delivery_id=manifest.delivery_id,
            dataset_type=manifest.dataset_type,
            source_system=manifest.source_system,
            contract_version=manifest.contract_version,
            manifest=manifest.payload(),
            manifest_digest=manifest.digest,
            mode=manifest.mode,
            period_start=manifest.period_start,
            period_end=manifest.period_end,
            snapshot_date=manifest.snapshot_date,
            confirmed_complete_through=manifest.confirmed_complete_through,
            evidence_ref=evidence_ref,
            approved_by=actor,
            cadence_days=cadence_days,
        )
        self._session.add(row)
        self._session.flush()
        self._session.add_all(
            [DeliveryPart(delivery_id=row.id, file_hash=h) for h in manifest.file_hashes]
        )
        return row

    def imports(self, delivery_id: UUID) -> list[DataImport]:
        return list(
            self._session.scalars(
                select(DataImport)
                .where(DataImport.delivery_id == delivery_id)
                .execution_options(populate_existing=True)
            )
        )

    def readiness(
        self, dataset_type: str, source_system: str | None = None
    ) -> DeliveryReadiness:
        statement = select(Delivery).where(Delivery.dataset_type == dataset_type)
        if source_system is not None:
            statement = statement.where(Delivery.source_system == source_system)
        deliveries = list(
            self._session.scalars(statement.execution_options(populate_existing=True))
        )
        candidates = [d for d in deliveries if d.status == "PUBLISHED"]
        published = [d for d in candidates if self.has_complete_parts(d)]
        damaged = len(published) != len(candidates)
        partial = damaged or any(d.status != "PUBLISHED" for d in deliveries)
        ids = tuple(
            sorted(
                (
                    i.id
                    for d in published
                    for i in self.imports(d.id)
                    if i.status == "COMPLETED"
                ),
                key=str,
            )
        )
        snapshot_ids = tuple(
            sorted(
                (
                    i.id
                    for d in published
                    if d.mode == DeliveryMode.SNAPSHOT and d.snapshot_date is not None
                    for i in self.imports(d.id)
                ),
                key=str,
            )
        )
        through = [
            d.confirmed_complete_through
            for d in published
            if d.confirmed_complete_through
        ]
        watermark = sha256(
            "|".join(sorted(d.manifest_digest for d in published)).encode()
        ).hexdigest()
        # Owner complete-through asserts coverage; never infer missing zeros.
        latest = (
            max(
                published,
                key=lambda d: d.confirmed_complete_through or date.min,
            )
            if published
            else None
        )
        return DeliveryReadiness(
            dataset_type,
            ids,
            max(through) if through else None,
            watermark,
            "PARTIAL" if partial else "COMPLETE" if published and through else "UNKNOWN",
            latest.cadence_days if latest else None,
            bool(snapshot_ids),
            "PUBLISHED_PARTS_INCOMPLETE"
            if damaged
            else "INCOMPLETE_DELIVERY"
            if partial
            else None
            if through
            else "COMPLETE_THROUGH_UNCONFIRMED",
            snapshot_approved_import_ids=snapshot_ids,
        )
