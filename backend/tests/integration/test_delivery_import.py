"""Native transactional integration with synthetic facts; NOT a PostgreSQL lock test."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.business.ingestion.delivery import DeliveryService
from app.business.ingestion.service import ImportService
from app.core.exceptions import ConflictError, ValidationError
from app.models import Base
from app.models.audit import AuditEvent
from app.models.data_import import DataImport
from app.models.enums import DatasetType
from app.repositories.analytics_metadata import SqlAlchemyAnalyticsMetadataRepository
from app.repositories.unit_of_work import SqlAlchemyUnitOfWork
from app.security.authorization import AuthorizationService
from app.shared.delivery import DeliveryEvidence, DeliveryManifest, DeliveryMode
from tests.unit.test_import_service import FakePipeline, FakeSourceFile, admin_context


@compiles(JSONB, "sqlite")
def sqlite_json(_type, _compiler, **_kw):
    return "JSON"


@pytest.fixture
def database():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    names = {
        "users",
        "regions",
        "hospitals",
        "data_imports",
        "deliveries",
        "delivery_parts",
        "audit_events",
        "data_quality_results",
        "quarantine_batches",
        "organization_aliases",
        "region_aliases",
        "profile_aliases",
        "mapping_state",
        "mapping_revisions",
    }
    Base.metadata.create_all(
        engine, tables=[t for t in Base.metadata.sorted_tables if t.name in names]
    )
    sessions = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def factory():
        with SqlAlchemyUnitOfWork(sessions) as uow:
            # SQLite has no PG advisory lock. Real concurrent test is separately opt-in.
            uow.deliveries.lock_source = lambda *_: None
            uow.mappings.lock = lambda: None
            yield uow

    yield sessions, factory
    engine.dispose()


@pytest.fixture
def delivery_setup(database, tmp_path):
    sessions, factory = database
    pipeline = FakePipeline(
        [
            FakeSourceFile("part-a.csv", tmp_path / "part-a.csv"),
            FakeSourceFile("part-b.csv", tmp_path / "part-b.csv"),
        ],
        hashes={"part-a.csv": "a" * 64, "part-b.csv": "b" * 64},
        rows=2,
        rejected=0,
    )
    pipeline.delivery_evidence = lambda _dataset, ids: DeliveryEvidence(
        len(ids) * 2, date(2025, 1, 1), date(2025, 1, 2), None
    )
    manifest = DeliveryManifest(
        "synthetic-1",
        "REFERRALS",
        "ИС БГ",
        "v1",
        DeliveryMode.DELTA,
        date(2025, 1, 1),
        date(2025, 1, 2),
        None,
        ("a" * 64, "b" * 64),
        4,
        "synthetic-contract",
        date(2025, 1, 2),
    )
    auth = AuthorizationService()
    context = replace(admin_context(), internal_user_id=None)
    delivery = DeliveryService(factory, auth, pipeline)
    delivery.approve(context, manifest, evidence_ref="synthetic-owner-evidence")
    return (
        sessions,
        factory,
        pipeline,
        manifest,
        context,
        delivery,
        ImportService(factory, auth, pipeline),
    )


def test_partial_delivery_hidden_then_retry_and_rename_idempotent(delivery_setup):
    sessions, factory, pipeline, manifest, context, delivery, service = delivery_setup
    pipeline.fail_on = {"part-b.csv"}
    report = service.import_dataset(context, DatasetType.REFERRALS, manifest=manifest)
    assert report.failed
    metadata = SqlAlchemyAnalyticsMetadataRepository(sessions)
    assert metadata.latest_completed_imports().import_ids == ()
    assert metadata.latest_import_summaries()[0].completeness == "PARTIAL"
    with factory() as uow:
        assert uow.deliveries.readiness("REFERRALS").completeness == "PARTIAL"
    pipeline.fail_on.clear()
    report = service.import_dataset(context, DatasetType.REFERRALS, manifest=manifest)
    assert not report.failed
    with factory() as uow:
        state = uow.deliveries.readiness("REFERRALS")
        assert state.completeness == "COMPLETE"
        assert state.confirmed_complete_through == date(2025, 1, 2)
        assert len(state.published_import_ids) == 2
    with sessions() as session:
        audit_count = session.scalar(select(func.count()).select_from(AuditEvent))
    old = metadata.latest_completed_imports()
    pipeline.files[0].name = "renamed.csv"
    pipeline.hashes["renamed.csv"] = "a" * 64
    service.import_dataset(context, DatasetType.REFERRALS, manifest=manifest)
    delivery.publish(context, manifest.delivery_id)
    assert metadata.latest_completed_imports() == old
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_count


def test_wrong_actual_period_fails_publication(delivery_setup):
    sessions, factory, pipeline, manifest, context, delivery, service = delivery_setup
    pipeline.delivery_evidence = lambda *_: DeliveryEvidence(
        4, date(2024, 12, 1), date(2025, 1, 2), None
    )
    with pytest.raises(ConflictError, match="EVENT_PERIOD_MISMATCH"):
        service.import_dataset(context, DatasetType.REFERRALS, manifest=manifest)
    assert (
        SqlAlchemyAnalyticsMetadataRepository(sessions)
        .latest_completed_imports()
        .import_ids
        == ()
    )


def test_changed_client_manifest_is_not_reviewed_evidence(delivery_setup):
    *_, manifest, context, delivery, service = delivery_setup
    with pytest.raises(ValidationError, match="CONTRACT_NOT_APPROVED"):
        service.import_dataset(
            context,
            DatasetType.REFERRALS,
            manifest=replace(manifest, period_end=date(2025, 1, 3)),
        )


def test_missing_part_does_not_process_anything(delivery_setup):
    _, _, pipeline, manifest, context, _, service = delivery_setup
    pipeline.files.pop()
    with pytest.raises(ValidationError, match="PARTS_MISMATCH"):
        service.import_dataset(context, DatasetType.REFERRALS, manifest=manifest)
    assert pipeline.processed == []


def test_changed_hash_overlap_is_blocked_by_reserved_period(delivery_setup):
    _, _, _, manifest, context, delivery, _ = delivery_setup
    with pytest.raises(ConflictError, match="OVERLAPPING_DELIVERY"):
        delivery.approve(
            context,
            replace(manifest, delivery_id="synthetic-2", file_hashes=("c" * 64,)),
            evidence_ref="synthetic",
        )


def test_crash_after_fact_write_recovers_uncompleted_file_only(
    delivery_setup, monkeypatch
):
    _, _, pipeline, manifest, context, _, service = delivery_setup
    complete = service._complete

    def crash(*_):
        raise RuntimeError("synthetic crash")

    monkeypatch.setattr(service, "_complete", crash)
    with pytest.raises(RuntimeError):
        service.import_dataset(context, DatasetType.REFERRALS, manifest=manifest)
    first = pipeline.processed[0]
    monkeypatch.setattr(service, "_complete", complete)
    service.import_dataset(context, DatasetType.REFERRALS, manifest=manifest)
    assert pipeline.rollbacks == [first]


def test_legacy_history_visible_but_not_operational(database):
    sessions, factory = database
    from datetime import UTC, datetime

    with sessions.begin() as session:
        row = DataImport(
            id=uuid4(),
            dataset_type="REFERRALS",
            source="ИС БГ",
            file_name="synthetic.csv",
            file_hash="c" * 64,
            status="COMPLETED",
            completed_at=datetime.now(UTC),
        )
        session.add(row)
    assert SqlAlchemyAnalyticsMetadataRepository(
        sessions
    ).latest_completed_imports().import_ids == (row.id,)
    with factory() as uow:
        assert uow.deliveries.readiness("REFERRALS").published_import_ids == ()


def test_recovery_reloads_after_source_lock_before_any_rollback(delivery_setup):
    _, factory, pipeline, manifest, context, _, importer = delivery_setup
    with factory() as uow:
        delivery_id = uow.deliveries.require(manifest.delivery_id).id
    import_id = importer._register_import(
        context,
        DatasetType.REFERRALS,
        pipeline.files[0],
        "a" * 64,
        delivery_id=delivery_id,
    )
    acquired = []
    rollbacks_at_publication = []

    @contextmanager
    def recovery_factory():
        with factory() as uow:

            def acquire(source, dataset):
                acquired.append((source, dataset))
                # Deterministic ordering: retry wins before recovery acquires lock.
                importer.import_dataset(context, DatasetType.REFERRALS, manifest=manifest)
                rollbacks_at_publication.extend(pipeline.rollbacks)

            uow.deliveries.lock_source = acquire
            yield uow

    recovery = ImportService(recovery_factory, AuthorizationService(), pipeline)
    with pytest.raises(ValidationError):
        recovery.recover(context, import_id)
    assert acquired == [(manifest.source_system, manifest.dataset_type)]
    assert pipeline.rollbacks == rollbacks_at_publication
    with factory() as uow:
        assert uow.data_imports.get(import_id).status == "COMPLETED"
        assert uow.deliveries.readiness("REFERRALS").completeness == "COMPLETE"


def test_recovery_keeps_source_lock_through_rollback_and_status_commit(delivery_setup):
    _, factory, pipeline, manifest, context, _, importer = delivery_setup
    with factory() as uow:
        delivery_id = uow.deliveries.require(manifest.delivery_id).id
    import_id = importer._register_import(
        context,
        DatasetType.REFERRALS,
        pipeline.files[0],
        "a" * 64,
        delivery_id=delivery_id,
    )
    locked = False
    observations = []

    @contextmanager
    def recovery_factory():
        nonlocal locked
        with factory() as uow:

            def acquire(*_):
                nonlocal locked
                locked = True

            uow.deliveries.lock_source = acquire
            update = uow.data_imports.update_status
            commit = uow.commit

            def checked_update(*args, **kwargs):
                observations.append(("update", locked))
                return update(*args, **kwargs)

            def checked_commit():
                observations.append(("commit", locked))
                commit()

            uow.data_imports.update_status = checked_update
            uow.commit = checked_commit
            yield uow
        locked = False

    def rollback(**_):
        observations.append(("rollback", locked))

    pipeline.rollback = rollback
    ImportService(recovery_factory, AuthorizationService(), pipeline).recover(
        context, import_id
    )
    assert observations == [("rollback", True), ("update", True), ("commit", True)]


@pytest.mark.parametrize("damage", ["failed", "missing", "hash", "count"])
def test_published_delivery_with_damaged_parts_never_certifies_subset(
    delivery_setup, damage
):
    sessions, factory, _, manifest, context, delivery, importer = delivery_setup
    importer.import_dataset(context, DatasetType.REFERRALS, manifest=manifest)
    with sessions.begin() as session:
        part = session.scalars(select(DataImport)).first()
        if damage == "failed":
            part.status = "FAILED"
        elif damage == "missing":
            session.delete(part)
        elif damage == "hash":
            part.file_hash = "f" * 64
        else:
            part.rows_loaded = 0
    with factory() as uow:
        readiness = uow.deliveries.readiness("REFERRALS")
        assert readiness.completeness == "PARTIAL"
        assert readiness.published_import_ids == ()
        assert readiness.confirmed_complete_through is None
        assert readiness.reason == "PUBLISHED_PARTS_INCOMPLETE"
    with pytest.raises(ConflictError, match="PUBLISHED_PARTS_INCOMPLETE"):
        delivery.publish(context, manifest.delivery_id)


def test_recovery_refuses_published_delivery_even_if_part_not_completed(delivery_setup):
    sessions, _, pipeline, manifest, context, _, importer = delivery_setup
    importer.import_dataset(context, DatasetType.REFERRALS, manifest=manifest)
    with sessions.begin() as session:
        part = session.scalars(select(DataImport)).first()
        part.status = "RUNNING"
        import_id = part.id
    with pytest.raises(ValidationError, match="PUBLISHED_DELIVERY"):
        importer.recover(context, import_id)
    assert pipeline.rollbacks == []


def test_mixed_waiting_delta_snapshot_age_uses_own_verified_snapshot_ids(database):
    from datetime import UTC, datetime

    from app.shared.analytics_data import RawWaitingSummary
    from tests.unit.test_analytics_service import DATE_FILTER, FakeCache, make_service

    sessions, factory = database
    context = replace(admin_context(), internal_user_id=None)

    class Evidence:
        current = None

        def delivery_evidence(self, *_):
            return self.current

    evidence = Evidence()
    delivery = DeliveryService(factory, AuthorizationService(), evidence)
    manifests = [
        DeliveryManifest(
            "delta",
            "WAITING",
            "ИС БГ",
            "v1",
            DeliveryMode.DELTA,
            date(2025, 1, 1),
            date(2025, 1, 2),
            None,
            ("c" * 64,),
            1,
            "synthetic",
            date(2025, 1, 2),
        ),
        DeliveryManifest(
            "snapshot",
            "WAITING",
            "ИС БГ",
            "v1",
            DeliveryMode.SNAPSHOT,
            None,
            None,
            date(2025, 2, 1),
            ("d" * 64,),
            1,
            "synthetic",
            date(2025, 2, 1),
        ),
    ]
    ids = []
    for manifest in manifests:
        delivery.approve(context, manifest, evidence_ref="synthetic-owner")
        with factory() as uow:
            delivery_id = uow.deliveries.require(manifest.delivery_id).id
        import_id = uuid4()
        ids.append(import_id)
        with sessions.begin() as session:
            session.add(
                DataImport(
                    id=import_id,
                    delivery_id=delivery_id,
                    dataset_type="WAITING",
                    source="ИС БГ",
                    file_name="synthetic",
                    file_hash=manifest.file_hashes[0],
                    status="COMPLETED",
                    completed_at=datetime.now(UTC),
                    rows_read=1,
                    rows_valid=1,
                    rows_rejected=0,
                    rows_loaded=1,
                )
            )
        evidence.current = DeliveryEvidence(
            1,
            date(2025, 1, 1),
            date(2025, 1, 2),
            date(2025, 3, 1)
            if manifest.mode == DeliveryMode.DELTA
            else manifest.snapshot_date,
        )
        delivery.publish(context, manifest.delivery_id)
    metadata = SqlAlchemyAnalyticsMetadataRepository(sessions)

    class QueryProbe:
        scope = None

        def waiting_summary(self, _filters, scope):
            self.scope = scope
            age = 59.0 if ids[0] in scope.published_import_ids else 31.0
            return RawWaitingSummary(
                datetime(2025, 2, 1, tzinfo=UTC), 1, 0, age, age, age, age
            )

    probe = QueryProbe()
    result = make_service(probe, metadata, FakeCache()).waiting_summary(
        context, DATE_FILTER
    )
    assert probe.scope.published_import_ids == (ids[1],)
    assert result.median_days.value == 31.0
    readiness = metadata.delivery_readiness("WAITING")
    assert set(readiness.published_import_ids) == set(ids)
    assert readiness.snapshot_approved_import_ids == (ids[1],)
