"""Real SQLAlchemy atomicity on a synthetic SQLite store; PG locks need opt-in tests."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.models.audit import AuditEvent
from app.models.system import SystemOperation


@compiles(JSONB, "sqlite")
def jsonb_for_synthetic_sqlite(element, compiler, **kw):
    return "JSON"


@compiles(PGUUID, "sqlite")
def uuid_for_synthetic_sqlite(element, compiler, **kw):
    return "CHAR(32)"


@pytest.fixture
def sessions():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def functions(connection, record):
        connection.create_function("pg_advisory_xact_lock", 1, lambda _key: None)
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def repository(sessions):
    from app.repositories.organization_forecasts import (
        SqlAlchemyOrganizationForecastRepository,
    )

    return SqlAlchemyOrganizationForecastRepository(sessions, history_repository=None)


def test_terminal_result_and_audit_commit_together_and_retry_reuses_result(sessions):
    repo = repository(sessions)
    operation_id = uuid4()
    result = {
        "operation_id": str(operation_id),
        "status": "SUPPRESSED",
        "reason": "MODEL_NOT_REGISTERED",
    }
    with repo.transaction(operation_id) as tx:
        assert tx.terminal_result() is None
        assert tx.finish(result) == result
    with repo.transaction(operation_id) as tx:
        assert tx.terminal_result() == result
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(SystemOperation)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert session.get(SystemOperation, operation_id).status == "COMPLETED"


def test_exception_after_finish_rolls_back_operation_and_audit_and_allows_retry(sessions):
    repo = repository(sessions)
    operation_id = uuid4()
    with pytest.raises(RuntimeError), repo.transaction(operation_id) as tx:
        tx.finish({"status": "SUPPRESSED", "reason": "SYNTHETIC"})
        raise RuntimeError("synthetic before commit")
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(SystemOperation)) == 1
        assert session.get(SystemOperation, operation_id).status == "FAILED"
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
    with repo.transaction(operation_id) as tx:
        assert tx.terminal_result() is None
        tx.finish({"status": "SUPPRESSED", "reason": "SYNTHETIC"})
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(SystemOperation)) == 1


def test_missing_mapping_publication_stops_before_aggregate_read(sessions):
    from tests.unit.test_organization_forecast import REQUEST

    repo = repository(sessions)
    with repo.transaction(uuid4()) as tx:
        assert tx.locked_input(REQUEST) is None


def test_enabled_worker_persists_safe_negative_without_touching_clickhouse(
    sessions, monkeypatch
):
    from app.adapters import organization_forecasting
    from app.core.config import Settings
    from app.database import clickhouse, postgres
    from app.workers.tasks import forecast_organization

    monkeypatch.setattr(
        organization_forecasting,
        "get_settings",
        lambda: Settings(app_secret="synthetic", organization_forecast_enabled=True),
    )
    monkeypatch.setattr(postgres, "get_session_factory", lambda: sessions)

    def forbidden():
        raise AssertionError("unapproved mapping must not read ClickHouse")

    monkeypatch.setattr(clickhouse, "get_client", forbidden)
    # Today's origin allows this test to reach the actual publication gate.
    result = forecast_organization.run(
        hospital_id=str(UUID(int=1)),
        model_version="synthetic-v1",
        mapping_version="none",
        delivery_watermark="none",
        origin=datetime.now(UTC).date().isoformat(),
    )
    assert result["reason"] == "APPROVED_INPUT_NOT_AVAILABLE"
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(SystemOperation)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_forecast_points_signal_and_both_audits_are_one_transaction(sessions):
    from app.models.analytics import Forecast
    from app.models.directory import Hospital, Region
    from app.models.forecast_point import ForecastPoint
    from app.models.signal import Signal
    from tests.unit.test_organization_forecast import HOSPITAL, REQUEST, configured

    service, store, _ = configured()
    result = service.run(REQUEST)
    operation_id = UUID(result["operation_id"])
    with sessions.begin() as session:
        region = Region(id=uuid4(), code="synthetic", name="Synthetic region")
        session.add(region)
        session.flush()
        session.add(
            Hospital(
                id=HOSPITAL,
                code="synthetic",
                name="Synthetic hospital",
                region_id=region.id,
            )
        )
        session.add(store.model)
    repo = repository(sessions)
    with pytest.raises(RuntimeError), repo.transaction(operation_id) as tx:
        tx.finish(
            result,
            forecast=store.forecasts[0],
            points=tuple(store.points),
            signal=store.signals[0],
        )
        raise RuntimeError("synthetic crash after flush before commit")
    with sessions() as session:
        assert session.get(SystemOperation, operation_id).status == "FAILED"
        for cls in (Forecast, ForecastPoint, Signal, AuditEvent):
            assert session.scalar(select(func.count()).select_from(cls)) == 0
    # Fresh objects after rollback; same identity recovers without stale session objects.
    service, store, _ = configured()
    result = service.run(REQUEST)
    with repo.transaction(operation_id) as tx:
        committed = tx.finish(
            result,
            forecast=store.forecasts[0],
            points=tuple(store.points),
            signal=store.signals[0],
        )
    with repo.transaction(operation_id) as tx:
        assert tx.terminal_result() == committed
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Forecast)) == 1
        assert session.scalar(select(func.count()).select_from(ForecastPoint)) == 7
        assert session.scalar(select(func.count()).select_from(Signal)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2
        assert session.scalar(select(func.count()).select_from(SystemOperation)) == 1


def seed_publication(sessions):
    from datetime import timedelta

    from app.models.data_import import DataImport
    from app.models.delivery import Delivery, DeliveryPart
    from app.models.directory import Hospital, Region
    from app.models.mapping import MappingRevision, MappingState
    from app.repositories.delivery import SqlAlchemyDeliveryRepository
    from app.shared.delivery import DeliveryManifest, DeliveryMode
    from app.shared.mapping import MappingSnapshot
    from tests.unit.test_organization_forecast import HOSPITAL, NOW

    snapshot = MappingSnapshot.from_rows(
        "map-v1",
        [("ORGANIZATION", "IS_BG:REFERRALS:RECEIVING", "synthetic-key", str(HOSPITAL))],
    )
    with sessions.begin() as session:
        region = Region(id=uuid4(), code="synthetic", name="Synthetic region")
        session.add(region)
        session.flush()
        session.add(
            Hospital(
                id=HOSPITAL,
                code="synthetic",
                name="Synthetic hospital",
                region_id=region.id,
            )
        )
        session.add(
            MappingState(id=1, generation=1, active_generation=1, active_version="map-v1")
        )
        session.add(
            MappingRevision(
                version="map-v1",
                generation=1,
                digest=snapshot.digest,
                rows=list(snapshot.rows()),
                actor="synthetic-reviewer",
                evidence_ref="synthetic-only",
                published_at=NOW,
            )
        )
        manifest = DeliveryManifest(
            "synthetic-delivery",
            "REFERRALS",
            "ИС БГ",
            "synthetic-v1",
            DeliveryMode.DELTA,
            NOW.date() - timedelta(days=42),
            NOW.date() - timedelta(days=1),
            None,
            ("a" * 64,),
            4200,
            "synthetic",
            NOW.date() - timedelta(days=1),
        )
        delivery = Delivery(
            id=uuid4(),
            delivery_id="synthetic-delivery",
            dataset_type="REFERRALS",
            source_system="ИС БГ",
            contract_version="synthetic",
            manifest=manifest.payload(),
            manifest_digest=manifest.digest,
            mode="DELTA",
            period_start=NOW.date() - timedelta(days=42),
            period_end=NOW.date() - timedelta(days=1),
            confirmed_complete_through=NOW.date() - timedelta(days=1),
            status="PUBLISHED",
            evidence_ref="synthetic-only",
            approved_by="synthetic-reviewer",
            approved_at=NOW,
            published_at=NOW,
        )
        session.add(delivery)
        session.flush()
        session.add(DeliveryPart(delivery_id=delivery.id, file_hash="a" * 64))
        file = DataImport(
            id=uuid4(),
            delivery_id=delivery.id,
            dataset_type="REFERRALS",
            source="ИС БГ",
            file_name="synthetic.csv",
            file_hash="a" * 64,
            rows_read=4200,
            rows_valid=4200,
            rows_loaded=4200,
            rows_rejected=0,
            status="COMPLETED",
            completed_at=NOW,
        )
        session.add(file)
        session.flush()
        return SqlAlchemyDeliveryRepository(session).readiness("REFERRALS")


def test_locked_d_contract_scopes_history_and_rechecks_revocation(sessions):
    from dataclasses import replace

    from app.models.mapping import MappingState
    from app.repositories.organization_forecasts import (
        SqlAlchemyOrganizationForecastRepository,
    )
    from app.shared.analytics_data import RawTimeSeriesPoint
    from tests.unit.test_organization_forecast import HISTORY, HOSPITAL, REQUEST

    delivery = seed_publication(sessions)

    class History:
        def referral_timeseries(self, filters, scope):
            assert filters.date_from.date() == HISTORY[0].observed_on
            assert filters.date_to.date() == HISTORY[-1].observed_on
            assert scope.canonical_hospital_ids == (HOSPITAL,)
            assert not scope.all_canonical and not scope.include_unmapped
            assert scope.mapping_version == "map-v1"
            assert scope.published_import_ids == delivery.published_import_ids
            return tuple(
                RawTimeSeriesPoint(
                    datetime.combine(p.observed_on, datetime.min.time(), UTC), p.count
                )
                for p in HISTORY
            )

    repo = SqlAlchemyOrganizationForecastRepository(
        sessions, history_repository=History()
    )
    request = replace(REQUEST, delivery_watermark=delivery.publication_watermark)
    with repo.transaction(uuid4()) as tx:
        data = tx.locked_input(request)
        assert data.hospital_id == HOSPITAL and data.history == HISTORY
        assert tx.recheck(request)
        # A revocation observed before persist invalidates the entire input snapshot.
        tx._session.get(MappingState, 1).generation = 2
        tx._session.flush()
        assert not tx.recheck(request)


def test_operation_audit_preserves_worker_request_id(sessions):
    from app.core.request_context import request_id_scope

    repo = repository(sessions)
    operation_id = uuid4()
    with request_id_scope("synthetic-r1-request"), repo.transaction(operation_id) as tx:
        tx.finish({"status": "SUPPRESSED", "reason": "SYNTHETIC"})
    with sessions() as session:
        assert session.scalar(select(AuditEvent)).request_id == "synthetic-r1-request"
        assert (
            session.get(SystemOperation, operation_id).request_id
            == "synthetic-r1-request"
        )


def test_running_reservation_visible_before_computation_and_failure_is_safe(sessions):
    repo = repository(sessions)
    operation_id = uuid4()
    with pytest.raises(RuntimeError), repo.transaction(operation_id):
        with sessions() as observer:
            row = observer.get(SystemOperation, operation_id)
            assert row.status == "RUNNING"
            assert row.started_at is not None
        raise RuntimeError("private object paths must not leak")
    with sessions() as observer:
        row = observer.get(SystemOperation, operation_id)
        assert row.status == "FAILED"
        assert row.error_summary == "ORGANIZATION_FORECAST_FAILED"
        assert observer.scalar(select(func.count()).select_from(AuditEvent)) == 0
    with repo.transaction(operation_id) as tx:
        assert tx.terminal_result() is None
        tx.finish({"status": "COMPLETED"})
    # A duplicate worker exception cannot overwrite the committed result.
    with pytest.raises(RuntimeError), repo.transaction(operation_id) as tx:
        assert tx.terminal_result() == {"status": "COMPLETED"}
        raise RuntimeError("duplicate failed after completion")
    with sessions() as observer:
        assert observer.get(SystemOperation, operation_id).status == "COMPLETED"
        assert observer.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_worker_termination_leaves_actionable_running_reservation(sessions):
    operation_id = uuid4()
    with pytest.raises(KeyboardInterrupt), repository(sessions).transaction(operation_id):
        raise KeyboardInterrupt()
    with sessions() as observer:
        assert observer.get(SystemOperation, operation_id).status == "RUNNING"
        assert observer.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_weekly_signal_persistence_deduplicates_changed_delivery(sessions):
    from dataclasses import replace

    from app.models.analytics import Forecast
    from app.models.signal import Signal
    from tests.unit.test_organization_forecast import REQUEST, configured

    seed_publication(sessions)
    service, store, _ = configured()
    first = service.run(REQUEST)
    store.input = replace(store.input, delivery_watermark="delivery-v2")
    second = service.run(replace(REQUEST, delivery_watermark="delivery-v2"))
    with sessions.begin() as session:
        session.add(store.model)
    repo = repository(sessions)
    persisted = []
    for index, result in enumerate((first, second)):
        with repo.transaction(UUID(result["operation_id"])) as tx:
            persisted.append(
                tx.finish(
                    result,
                    forecast=store.forecasts[index],
                    points=tuple(store.points[index * 7 : (index + 1) * 7]),
                    signal=store.signals[index],
                )
            )
    assert persisted[0]["signal_id"] == persisted[1]["signal_id"]
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 1
        assert session.scalar(select(func.count()).select_from(Forecast)) == 2
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 3
