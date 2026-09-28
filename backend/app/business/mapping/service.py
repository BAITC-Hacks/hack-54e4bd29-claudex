"""Auditable mapping decisions, fail-closed invalidation and verified publication."""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from app.business.mapping.ports import MappingProjection
from app.business.ports import UnitOfWorkFactory
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_request_id
from app.models.enums import AuditAction, AuditEntityType, MappingMethod, MappingStatus
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.permissions import Permission
from app.shared.mapping import (
    ORGANIZATION_SPACES,
    REGION_SPACES,
    MappingReviewItem,
    MappingSnapshot,
)


class MappingService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        authorization: AuthorizationService,
        projection: MappingProjection,
    ) -> None:
        self._uow_factory = uow_factory
        self._authz = authorization
        self._projection = projection

    def _authorize(self, context: SecurityContext) -> None:
        self._authz.require_permission(context, Permission.MAPPING_MANAGE)
        if not context.scope.resolved or not context.scope.is_global:
            raise ForbiddenError("GLOBAL_SCOPE_REQUIRED")

    def review(
        self,
        context: SecurityContext,
        *,
        kind: str,
        status: str | None = None,
        limit: int = 100,
    ) -> tuple[list[MappingReviewItem], int]:
        """List exact source identities for a human reviewer; never infer a match."""
        self._authorize(context)
        if kind not in {"ORGANIZATION", "REGION", "PROFILE"}:
            raise ValidationError("INVALID_MAPPING_KIND")
        if status not in {None, "UNMAPPED", "MAPPED", "REVIEW_REQUIRED"}:
            raise ValidationError("INVALID_MAPPING_STATUS")
        if limit < 1:
            raise ValidationError("INVALID_REVIEW_LIMIT")
        with self._uow_factory() as uow:
            return uow.mappings.review(kind=kind, status=status, limit=min(limit, 100))

    def register(
        self,
        context: SecurityContext,
        *,
        kind: str,
        source_system: str,
        identity_space: str,
        source_key: str,
    ) -> UUID:
        self._authorize(context)
        self._identity(kind, identity_space)
        expected_source = "ИС БГ" if identity_space.startswith("IS_BG:") else "ЭРСБ"
        if (
            source_system not in {expected_source, identity_space.split(":")[0]}
            or not source_key.strip()
        ):
            raise ValidationError("INVALID_SOURCE_IDENTITY")
        with self._uow_factory() as uow:
            uow.mappings.lock()
            alias = uow.mappings.register(
                kind=kind,
                source_system=expected_source,
                identity_space=identity_space,
                source_key=source_key,
            )
            alias_id = alias.id
            uow.commit()
        return alias_id

    def _identity(self, kind: str, space: str) -> None:
        spaces = (
            ORGANIZATION_SPACES
            if kind == "ORGANIZATION"
            else REGION_SPACES
            if kind == "REGION"
            else ()
        )
        if space not in spaces:
            raise ValidationError("IDENTITY_SPACE_UNCONFIRMED")

    def approve(
        self,
        context: SecurityContext,
        alias_id: UUID,
        hospital_id: UUID,
        evidence_ref: str,
        expected_version: int,
    ) -> str:
        return self._decide(
            context, alias_id, hospital_id, evidence_ref, expected_version, "ORGANIZATION"
        )

    def approve_region(
        self,
        context: SecurityContext,
        alias_id: UUID,
        region_id: UUID,
        evidence_ref: str,
        expected_version: int,
    ) -> str:
        return self._decide(
            context, alias_id, region_id, evidence_ref, expected_version, "REGION"
        )

    def revoke(
        self,
        context: SecurityContext,
        alias_id: UUID,
        reason: str,
        expected_version: int,
        *,
        kind: str = "ORGANIZATION",
    ) -> str:
        return self._decide(context, alias_id, None, reason, expected_version, kind)

    def _decide(
        self,
        context: SecurityContext,
        alias_id: UUID,
        target_id: UUID | None,
        evidence_ref: str,
        expected_version: int,
        kind: str,
    ) -> str:
        self._authorize(context)
        if not evidence_ref.strip():
            raise ValidationError("OWNER_EVIDENCE_REQUIRED")
        with self._uow_factory() as uow:
            repo = uow.mappings
            repo.lock()
            alias = repo.get_alias(alias_id, kind)
            if alias is None:
                raise NotFoundError()
            if alias.version != expected_version:
                raise ConflictError("STALE_MAPPING_VERSION")
            self._identity(kind, alias.identity_space)
            if target_id is not None:
                if alias.mapping_status == "REVIEW_REQUIRED":
                    raise ConflictError("REVIEW_REQUIRED")
                if not repo.target_exists(target_id, kind):
                    raise NotFoundError()
                current = getattr(
                    alias, "hospital_id" if kind == "ORGANIZATION" else "region_id"
                )
                if current is not None and current != target_id:
                    raise ConflictError("REVOKE_BEFORE_REASSIGNMENT")
            setattr(
                alias, "hospital_id" if kind == "ORGANIZATION" else "region_id", target_id
            )
            alias.mapping_status = (
                MappingStatus.MAPPED if target_id else MappingStatus.UNMAPPED
            )
            alias.mapping_method = MappingMethod.MANUAL_APPROVED if target_id else None
            alias.version += 1
            version = repo.record_decision(
                actor=context.user_id, evidence_ref=evidence_ref
            )
            uow.audit.append(
                actor_user_id=context.internal_user_id,
                action=AuditAction.MAPPING_APPROVED
                if target_id
                else AuditAction.MAPPING_REVOKED,
                entity_type=AuditEntityType.MAPPING,
                entity_id=alias_id,
                request_id=get_request_id(),
                metadata={
                    "version": version,
                    "alias_version": alias.version,
                    "actor": context.user_id,
                    "evidence_ref": evidence_ref,
                    "target_id": str(target_id) if target_id else None,
                    "kind": kind,
                },
            )
            uow.commit()
        return version

    def publish(self, context: SecurityContext, version: str) -> MappingSnapshot:
        self._authorize(context)
        with self._uow_factory() as uow:
            uow.mappings.lock()
            snapshot = uow.mappings.candidate(version)
            self._projection.publish(snapshot)
            uow.mappings.activate(version)
            uow.audit.append(
                actor_user_id=context.internal_user_id,
                action=AuditAction.MAPPING_PUBLISHED,
                entity_type=AuditEntityType.MAPPING,
                entity_id=uuid5(NAMESPACE_URL, version),
                request_id=get_request_id(),
                metadata={
                    "version": version,
                    "digest": snapshot.digest,
                    "actor": context.user_id,
                },
            )
            uow.commit()
        return snapshot
