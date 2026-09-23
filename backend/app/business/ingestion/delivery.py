"""Delivery policy and reviewed manifest lifecycle."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from app.business.ingestion.ports import DeliveryEvidenceReader
from app.business.ports import UnitOfWorkFactory
from app.core.exceptions import ConflictError, ValidationError
from app.core.logging import get_request_id
from app.models.enums import AuditAction, AuditEntityType
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.permissions import Permission
from app.shared.delivery import DeliveryEvidence, DeliveryManifest, DeliveryMode


def assess_delivery(
    manifest: DeliveryManifest,
    *,
    received_hashes: frozenset[str],
    overlaps_published_period: bool,
    contract_approved: bool,
) -> tuple[bool, str]:
    if not contract_approved:
        return False, "CONTRACT_NOT_APPROVED"
    if (
        not manifest.delivery_id
        or not manifest.source_system
        or not manifest.schema_version
        or not manifest.contract_version
        or manifest.dataset_type not in {"REFERRALS", "WAITING", "REFUSALS", "TREATED"}
        or not manifest.file_hashes
        or len(set(manifest.file_hashes)) != len(manifest.file_hashes)
        or any(re.fullmatch(r"[0-9a-f]{64}", h) is None for h in manifest.file_hashes)
        or (manifest.expected_rows is not None and manifest.expected_rows < 0)
    ):
        return False, "INVALID_MANIFEST"
    if set(manifest.file_hashes) != received_hashes:
        return False, "PARTS_MISMATCH"
    if manifest.mode == DeliveryMode.REPLACEMENT:
        return False, "REPLACEMENT_NOT_SUPPORTED"
    if manifest.mode == DeliveryMode.SNAPSHOT:
        if manifest.snapshot_date is None:
            return False, "UNKNOWN_SNAPSHOT_DATE"
    elif manifest.period_start is None or manifest.period_end is None:
        return False, "UNKNOWN_PERIOD"
    elif manifest.period_start > manifest.period_end:
        return False, "INVALID_PERIOD"
    if manifest.confirmed_complete_through is not None:
        bound = (
            manifest.snapshot_date
            if manifest.mode == DeliveryMode.SNAPSHOT
            else manifest.period_end
        )
        if bound != manifest.confirmed_complete_through:
            return False, "INVALID_COMPLETE_THROUGH"
    if overlaps_published_period:
        return False, "OVERLAPPING_DELIVERY"
    return True, "READY"


class DeliveryService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        authorization: AuthorizationService,
        evidence_reader: DeliveryEvidenceReader | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._authz = authorization
        self._evidence_reader = evidence_reader

    def approve(
        self,
        context: SecurityContext,
        manifest: DeliveryManifest,
        *,
        evidence_ref: str,
        cadence_days: int | None = None,
        legacy_complete_through: date | None = None,
    ) -> str:
        """Explicit operator review. Never called by ordinary import submission."""
        self._authz.require_permission(context, Permission.DELIVERY_APPROVE)
        if not context.scope.is_global or not context.scope.resolved:
            raise ValidationError("GLOBAL_SCOPE_REQUIRED")
        if not evidence_ref.strip() or (cadence_days is not None and cadence_days <= 0):
            raise ValidationError("OWNER_EVIDENCE_REQUIRED")
        ready, reason = assess_delivery(
            manifest,
            received_hashes=frozenset(manifest.file_hashes),
            overlaps_published_period=False,
            contract_approved=True,
        )
        if not ready:
            raise ValidationError(reason)
        with self._uow_factory() as uow:
            repo = uow.deliveries
            repo.lock_source(manifest.source_system, manifest.dataset_type)
            existing = repo.get(manifest.delivery_id)
            if existing is not None:
                if existing.manifest_digest != manifest.digest:
                    raise ConflictError("MANIFEST_CHANGED")
                return existing.manifest_digest
            if repo.overlaps(manifest):
                raise ConflictError("OVERLAPPING_DELIVERY")
            if repo.has_legacy(manifest.source_system, manifest.dataset_type):
                # Baseline coverage requires external evidence, never a load timestamp.
                start = (
                    manifest.snapshot_date
                    if manifest.mode == DeliveryMode.SNAPSHOT
                    else manifest.period_start
                )
                if (
                    start is None
                    or legacy_complete_through is None
                    or start <= legacy_complete_through
                ):
                    raise ConflictError("LEGACY_COVERAGE_REVIEW_REQUIRED")
            row = repo.add_approved(
                manifest,
                evidence_ref=evidence_ref,
                actor=context.user_id,
                cadence_days=cadence_days,
            )
            uow.audit.append(
                actor_user_id=context.internal_user_id,
                action=AuditAction.DELIVERY_APPROVED,
                entity_type=AuditEntityType.DELIVERY,
                entity_id=row.id,
                request_id=get_request_id(),
                metadata={
                    "digest": manifest.digest,
                    "evidence_ref": evidence_ref,
                    "actor": context.user_id,
                    "legacy_complete_through": str(legacy_complete_through)
                    if legacy_complete_through
                    else None,
                },
            )
            uow.commit()
        return manifest.digest

    def publish(self, context: SecurityContext, delivery_id: str) -> None:
        self._authz.require_permission(context, Permission.DATA_IMPORT_CREATE)
        with self._uow_factory() as uow:
            row = uow.deliveries.require(delivery_id)
            uow.deliveries.lock_source(row.source_system, row.dataset_type)
            row = uow.deliveries.require(delivery_id, refresh=True)
            if row.status == "PUBLISHED":
                if not uow.deliveries.has_complete_parts(row):
                    raise ConflictError("PUBLISHED_PARTS_INCOMPLETE")
                return
            imports = uow.deliveries.imports(row.id)
            manifest = DeliveryManifest.from_payload(row.manifest)
            ready, reason = assess_delivery(
                manifest,
                received_hashes=frozenset(
                    i.file_hash for i in imports if i.status == "COMPLETED"
                ),
                overlaps_published_period=uow.deliveries.overlaps(manifest),
                contract_approved=bool(
                    row.approved_at and row.manifest_digest == manifest.digest
                ),
            )
            if ready and (
                manifest.expected_rows is None
                or sum(i.rows_read for i in imports) != manifest.expected_rows
            ):
                ready, reason = False, "ROW_COUNT_UNCONFIRMED"
            if ready and any(
                i.rows_loaded != i.rows_valid
                or i.rows_read != i.rows_valid + i.rows_rejected
                or i.rows_rejected
                for i in imports
            ):
                ready, reason = False, "ROW_COUNTS_NOT_COMPLETE"
            if ready:
                evidence = (
                    self._evidence_reader.delivery_evidence(
                        row.dataset_type, tuple(i.id for i in imports)
                    )
                    if self._evidence_reader
                    else None
                )
                ready, reason = assess_evidence(manifest, evidence)
            if not ready:
                row.status = "PARTIAL"
                row.reason = reason
                uow.commit()
                raise ConflictError(reason)
            row.status = "PUBLISHED"
            row.reason = None
            row.published_at = datetime.now(UTC)
            uow.audit.append(
                actor_user_id=context.internal_user_id,
                action=AuditAction.DELIVERY_PUBLISHED,
                entity_type=AuditEntityType.DELIVERY,
                entity_id=row.id,
                request_id=get_request_id(),
                metadata={"digest": manifest.digest},
            )
            uow.commit()


def assess_evidence(
    manifest: DeliveryManifest, evidence: DeliveryEvidence | None
) -> tuple[bool, str]:
    if evidence is None:
        return False, "EVENT_EVIDENCE_UNAVAILABLE"
    if manifest.expected_rows is None or evidence.rows != manifest.expected_rows:
        return False, "ANALYTICAL_COUNT_MISMATCH"
    if manifest.mode == DeliveryMode.SNAPSHOT:
        if (
            evidence.snapshot_date is None
            or evidence.snapshot_date != manifest.snapshot_date
        ):
            return False, "SNAPSHOT_MISMATCH"
    elif (
        evidence.event_period_start is None
        or evidence.event_period_end is None
        or manifest.period_start is None
        or manifest.period_end is None
        or evidence.event_period_start < manifest.period_start
        or evidence.event_period_end > manifest.period_end
    ):
        return False, "EVENT_PERIOD_MISMATCH"
    return True, "VERIFIED"
