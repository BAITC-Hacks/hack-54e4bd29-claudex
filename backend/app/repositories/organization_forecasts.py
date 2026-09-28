"""Single PostgreSQL transaction for forecast identity, publication locks and audit."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.request_context import get_request_id
from app.models.analytics import Forecast
from app.models.audit import AuditEvent
from app.models.directory import Hospital
from app.models.enums import AuditAction, AuditEntityType, DatasetType, SourceSystem
from app.models.forecast_point import ForecastPoint
from app.models.model_version import ModelVersion
from app.models.signal import Signal
from app.models.system import OperationStatus, SystemOperation
from app.repositories.delivery import SqlAlchemyDeliveryRepository
from app.repositories.mapping import SqlAlchemyMappingRepository
from app.repositories.signals import SqlAlchemySignalRepository
from app.shared.analytics_contracts import AnalyticsFilter
from app.shared.analytics_data import QueryScope, RawTimeSeriesPoint
from app.shared.forecasting import (
    DailyReferralCount,
    OrganizationForecastInput,
    OrganizationForecastRequest,
)


class ApprovedHistory(Protocol):
    def referral_timeseries(
        self, filters: AnalyticsFilter, scope: QueryScope
    ) -> tuple[RawTimeSeriesPoint, ...]: ...


class SqlAlchemyOrganizationForecastRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        history_repository: ApprovedHistory | None,
    ) -> None:
        self._sessions = session_factory
        self._history = history_repository

    @contextmanager
    def transaction(
        self, operation_id: UUID
    ) -> Iterator[OrganizationForecastTransaction]:
        key = int.from_bytes(operation_id.bytes[:8], "big", signed=True)
        # Commit visibility before potentially long inference. A killed worker leaves
        # RUNNING; retry acquires the same lock and resumes without a second result.
        with self._sessions() as session, session.begin():
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            operation = session.get(SystemOperation, operation_id)
            if operation is None:
                operation = SystemOperation(
                    id=operation_id,
                    operation_type="ml.forecast_organization",
                    request_id=get_request_id(),
                )
                session.add(operation)
            elif operation.operation_type != "ml.forecast_organization":
                raise ValueError("OPERATION_ID_COLLISION")
            if operation.status != OperationStatus.COMPLETED:
                operation.status = OperationStatus.RUNNING
                operation.started_at = datetime.now(UTC)
                operation.completed_at = None
                operation.error_summary = None
        try:
            with self._sessions() as session, session.begin():
                session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
                yield OrganizationForecastTransaction(
                    session, operation_id, self._history
                )
        except Exception:
            # Domain rows and completion audit rolled back together. Never replace a
            # competing worker's successful commit; exception text stays in logs.
            with self._sessions() as session, session.begin():
                session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
                operation = session.get(SystemOperation, operation_id)
                if (
                    operation is not None
                    and operation.status != OperationStatus.COMPLETED
                ):
                    operation.status = OperationStatus.FAILED
                    operation.completed_at = datetime.now(UTC)
                    operation.error_summary = "ORGANIZATION_FORECAST_FAILED"
            raise


class OrganizationForecastTransaction:
    def __init__(
        self, session: Session, operation_id: UUID, history: ApprovedHistory | None
    ) -> None:
        self._session = session
        self._id = operation_id
        self._history = history
        self._mapping = SqlAlchemyMappingRepository(session)
        self._delivery = SqlAlchemyDeliveryRepository(session)
        self._scope_snapshot: tuple[object, object] | None = None

    def terminal_result(self) -> dict[str, object] | None:
        operation = self._session.get(SystemOperation, self._id)
        if operation is not None and operation.status == OperationStatus.COMPLETED:
            if operation.operation_type != "ml.forecast_organization":
                raise ValueError("OPERATION_ID_COLLISION")
            return dict(operation.result or {})
        return None

    def registered_model(self, version: str) -> ModelVersion | None:
        # Model metadata cannot be revoked/edited while inference is committing.
        return self._session.scalar(
            select(ModelVersion)
            .where(ModelVersion.version == version)
            .with_for_update(read=True)
        )

    def locked_input(
        self, request: OrganizationForecastRequest
    ) -> OrganizationForecastInput | None:
        # This exact order is shared with D publication/revocation. Hold through commit.
        self._mapping.lock()
        self._delivery.lock_source(SourceSystem.IS_BG, DatasetType.REFERRALS)
        mapping = self._mapping.readiness()
        delivery = self._delivery.readiness(
            DatasetType.REFERRALS, source_system=SourceSystem.IS_BG
        )
        if (
            not mapping.verified
            or mapping.version != request.mapping_version
            or delivery.completeness != "COMPLETE"
            or not delivery.published_import_ids
            or delivery.publication_watermark != request.delivery_watermark
            or delivery.confirmed_complete_through is None
            or delivery.confirmed_complete_through < request.origin - timedelta(days=1)
        ):
            return None
        hospital = self._session.scalar(
            select(Hospital)
            .where(Hospital.id == request.hospital_id, Hospital.is_active.is_(True))
            .with_for_update(read=True, of=Hospital)
        )
        if hospital is None:
            return None
        snapshot = self._mapping.candidate(request.mapping_version)
        if not any(
            m.hospital_id == request.hospital_id
            and m.identity_space == "IS_BG:REFERRALS:RECEIVING"
            for m in snapshot.organizations
        ):
            return None
        if self._history is None:
            return None
        scope = QueryScope(
            canonical_hospital_ids=(request.hospital_id,),
            all_canonical=False,
            include_unmapped=False,
            mapping_version=request.mapping_version,
            published_import_ids=delivery.published_import_ids,
        )
        filters = AnalyticsFilter(
            datetime.combine(
                request.origin - timedelta(days=42), datetime.min.time(), UTC
            ),
            datetime.combine(
                request.origin - timedelta(days=1), datetime.max.time(), UTC
            ),
        )
        rows = self._history.referral_timeseries(filters, scope)
        self._scope_snapshot = (mapping, delivery)
        # Missing dates remain missing. A complete-through date alone never invents zeros.
        return OrganizationForecastInput(
            hospital_id=request.hospital_id,
            mapping_version=request.mapping_version,
            history=tuple(
                DailyReferralCount(p.period_start.date(), p.value) for p in rows
            ),
            delivery_watermark=delivery.publication_watermark,
            as_of=datetime.now(UTC),
            coverage_complete=True,
        )

    def recheck(self, request: OrganizationForecastRequest) -> bool:
        mapping = self._mapping.readiness()
        delivery = self._delivery.readiness(
            DatasetType.REFERRALS, source_system=SourceSystem.IS_BG
        )
        return (
            self._scope_snapshot == (mapping, delivery)
            and mapping.verified
            and mapping.version == request.mapping_version
            and delivery.completeness == "COMPLETE"
            and delivery.publication_watermark == request.delivery_watermark
        )

    def finish(
        self,
        result: dict[str, object],
        *,
        forecast: Forecast | None = None,
        points: tuple[ForecastPoint, ...] = (),
        signal: Signal | None = None,
    ) -> dict[str, object]:
        result = dict(result)
        if forecast is not None:
            self._session.add(forecast)
            self._session.flush()
            self._session.add_all(points)
            self._session.flush()
        if signal is not None:
            episode_key = int.from_bytes(signal.id.bytes[:8], "big", signed=True)
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": episode_key}
            )
            existing = self._session.get(Signal, signal.id)
            if existing is None:
                persisted, created = SqlAlchemySignalRepository(
                    self._session
                ).add_if_absent(signal)
            else:
                persisted, created = existing, False
            result["signal_id"] = str(persisted.id)
            if created:
                self._session.add(
                    AuditEvent(
                        action=AuditAction.SIGNAL_CREATED,
                        entity_type=AuditEntityType.SIGNAL,
                        entity_id=persisted.id,
                        actor_user_id=None,
                        request_id=get_request_id(),
                        event_metadata={
                            "scope_type": "HOSPITAL",
                            "rule_code": signal.rule_code,
                            "dedup_key": signal.dedup_key,
                            "operation_id": str(self._id),
                        },
                    )
                )
        operation = self._session.get(SystemOperation, self._id)
        if operation is None:
            operation = SystemOperation(
                id=self._id,
                operation_type="ml.forecast_organization",
                request_id=get_request_id(),
            )
            self._session.add(operation)
        operation.status = OperationStatus.COMPLETED
        operation.completed_at = datetime.now(UTC)
        operation.result = result
        operation.error_summary = None
        self._session.add(
            AuditEvent(
                action=AuditAction.ORGANIZATION_FORECAST_COMPLETED,
                entity_type=AuditEntityType.SYSTEM_OPERATION,
                entity_id=self._id,
                actor_user_id=None,
                request_id=get_request_id(),
                event_metadata=dict(result),
            )
        )
        self._session.flush()
        return result
