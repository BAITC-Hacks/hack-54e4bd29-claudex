"""Opt-in real PG source-lock race test. Creates only a unique test-owned schema."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from threading import Barrier, Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.business.ingestion.delivery import DeliveryService
from app.business.ingestion.service import ImportService
from app.core.exceptions import ConflictError, ValidationError
from app.models import Base
from app.models.enums import DatasetType
from app.repositories.unit_of_work import SqlAlchemyUnitOfWork
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role, SecurityContext
from app.shared.delivery import DeliveryEvidence, DeliveryManifest, DeliveryMode
from tests.unit.test_import_service import FakePipeline, FakeSourceFile

pytestmark = pytest.mark.skipif(
    not os.getenv("D_TEST_POSTGRES_DSN"),
    reason="isolated D_TEST_POSTGRES_DSN required; no application DB fallback",
)


@pytest.fixture
def pg_factory():
    assert (
        os.getenv("D_TEST_ALLOW_ISOLATED") == "1"
    ), "explicit isolated runtime opt-in required"
    dsn = os.environ["D_TEST_POSTGRES_DSN"]
    schema = "phase8-d-" + uuid4().hex
    admin = create_engine(dsn, connect_args={"connect_timeout": 5})
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        dsn,
        connect_args={
            "connect_timeout": 5,
            "options": "-clock_timeout=5000",
        },
    )

    @event.listens_for(engine, "connect")
    def set_test_schema(connection, _record):
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        connection.commit()

    names = {
        "users",
        "regions",
        "hospitals",
        "data_imports",
        "deliveries",
        "delivery_parts",
        "audit_events",
    }
    Base.metadata.create_all(
        engine, tables=[t for t in Base.metadata.sorted_tables if t.name in names]
    )
    sessions = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def factory():
        with SqlAlchemyUnitOfWork(sessions) as uow:
            yield uow

    try:
        yield factory
    finally:
        engine.dispose()
        # Only the UUID-named schema created above belongs to this test.
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_concurrent_source_period_reservations_have_one_winner(pg_factory):
    service = DeliveryService(pg_factory, AuthorizationService())
    context = SecurityContext(
        user_id="synthetic", roles=frozenset({Role.ADMIN}), scope=DataScope.global_scope()
    )
    manifest = DeliveryManifest(
        "synthetic-a",
        "REFERRALS",
        "ИС БГ",
        "v1",
        DeliveryMode.DELTA,
        date(2025, 1, 1),
        date(2025, 1, 2),
        None,
        ("a" * 64,),
        2,
        "synthetic-contract",
    )
    barrier = Barrier(2)

    def reserve(suffix):
        barrier.wait(timeout=5)
        try:
            service.approve(
                context,
                replace(manifest, delivery_id=suffix, file_hashes=(suffix[-1] * 64,)),
                evidence_ref="synthetic-owner",
            )
            return "APPROVED"
        except ConflictError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(reserve, ["synthetic-a", "synthetic-b"]))
    assert sorted(results) == ["APPROVED", "OVERLAPPING_DELIVERY"]


def _wait_for_advisory_waiter(factory, pid):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        with factory() as uow:
            waiting = uow.session.scalar(
                text(
                    "SELECT count(*) FROM pg_locks WHERE pid=:pid "
                    "AND locktype='advisory' AND NOT granted"
                ),
                {"pid": pid},
            )
        if waiting:
            return
        sleep(0.01)
    pytest.fail("competing operation did not wait on the source advisory lock")


def _recoverable_import(factory, tmp_path):
    pipeline = FakePipeline(
        [FakeSourceFile("synthetic.csv", tmp_path / "synthetic.csv")],
        hashes={"synthetic.csv": "a" * 64},
        rows=2,
        rejected=0,
    )
    pipeline.delivery_evidence = lambda *_: DeliveryEvidence(
        2, date(2025, 1, 1), date(2025, 1, 2), None
    )
    context = SecurityContext(
        user_id="synthetic", roles=frozenset({Role.ADMIN}), scope=DataScope.global_scope()
    )
    manifest = DeliveryManifest(
        "synthetic-recovery",
        "REFERRALS",
        "ИС БГ",
        "v1",
        DeliveryMode.DELTA,
        date(2025, 1, 1),
        date(2025, 1, 2),
        None,
        ("a" * 64,),
        2,
        "synthetic-contract",
        date(2025, 1, 2),
    )
    DeliveryService(factory, AuthorizationService(), pipeline).approve(
        context, manifest, evidence_ref="synthetic-owner"
    )
    importer = ImportService(factory, AuthorizationService(), pipeline)
    with factory() as uow:
        delivery_id = uow.deliveries.require(manifest.delivery_id).id
    import_id = importer._register_import(
        context,
        DatasetType.REFERRALS,
        pipeline.files[0],
        "a" * 64,
        delivery_id=delivery_id,
    )
    return pipeline, context, manifest, importer, import_id


def _waiter_factory(factory, attempted, pid):
    @contextmanager
    def wrapped():
        with factory() as uow:
            lock = uow.deliveries.lock_source

            def wait_for_source(source, dataset):
                pid.append(uow.session.scalar(text("SELECT pg_backend_pid()")))
                attempted.set()
                lock(source, dataset)

            uow.deliveries.lock_source = wait_for_source
            yield uow

    return wrapped


def test_recovery_waits_for_retry_then_refuses_completed_publication(
    pg_factory, tmp_path
):
    pipeline, context, manifest, importer, import_id = _recoverable_import(
        pg_factory, tmp_path
    )
    processing, release, attempted = Event(), Event(), Event()
    pid = []
    process = pipeline.process

    def blocked_process(**kwargs):
        processing.set()
        assert release.wait(4), "test did not release synthetic processing"
        return process(**kwargs)

    pipeline.process = blocked_process
    recovery = ImportService(
        _waiter_factory(pg_factory, attempted, pid), AuthorizationService(), pipeline
    )
    with ThreadPoolExecutor(max_workers=2) as workers:
        retry = workers.submit(
            importer.import_dataset, context, DatasetType.REFERRALS, manifest=manifest
        )
        assert processing.wait(3)
        stale_recover = workers.submit(recovery.recover, context, import_id)
        try:
            assert attempted.wait(3)
            _wait_for_advisory_waiter(pg_factory, pid[0])
            assert not stale_recover.done()
        finally:
            release.set()
        assert not retry.result(timeout=5).failed
        with pytest.raises(ValidationError):
            stale_recover.result(timeout=5)
    # Retry cleaned the initially RUNNING attempt once; recovery never deletes
    # facts after retry completion/publication.
    assert pipeline.rollbacks == [import_id]
    with pg_factory() as uow:
        assert uow.data_imports.get(import_id).status == "COMPLETED"
        assert uow.deliveries.require(manifest.delivery_id).status == "PUBLISHED"
        assert uow.deliveries.readiness("REFERRALS").completeness == "COMPLETE"


def test_retry_waits_until_recovery_cleanup_and_status_commit(pg_factory, tmp_path):
    pipeline, context, manifest, recovery, import_id = _recoverable_import(
        pg_factory, tmp_path
    )
    cleaning, release, attempted = Event(), Event(), Event()
    pid = []
    rollback = pipeline.rollback

    def blocked_rollback(**kwargs):
        if not cleaning.is_set():
            cleaning.set()
            assert release.wait(4), "test did not release synthetic cleanup"
        rollback(**kwargs)

    pipeline.rollback = blocked_rollback
    retry = ImportService(
        _waiter_factory(pg_factory, attempted, pid), AuthorizationService(), pipeline
    )
    with ThreadPoolExecutor(max_workers=2) as workers:
        recovered = workers.submit(recovery.recover, context, import_id)
        assert cleaning.wait(3)
        imported = workers.submit(
            retry.import_dataset, context, DatasetType.REFERRALS, manifest=manifest
        )
        try:
            assert attempted.wait(3)
            _wait_for_advisory_waiter(pg_factory, pid[0])
            assert not imported.done()
        finally:
            release.set()
        recovered.result(timeout=5)
        assert not imported.result(timeout=5).failed
    with pg_factory() as uow:
        assert uow.data_imports.get(import_id).status == "COMPLETED"
        assert uow.deliveries.require(manifest.delivery_id).status == "PUBLISHED"
        assert uow.deliveries.readiness("REFERRALS").completeness == "COMPLETE"
