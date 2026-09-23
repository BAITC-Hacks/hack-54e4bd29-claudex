"""Opt-in PostgreSQL race proof. Uses only a dedicated phase8-* database/schema."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.models import Base
from app.models.audit import AuditEvent
from app.models.system import SystemOperation
from app.repositories.organization_forecasts import (
    SqlAlchemyOrganizationForecastRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def pg_sessions():
    dsn = os.getenv("R1_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Dedicated phase8-* PostgreSQL unavailable; no live race claim")
    if not (make_url(dsn).database or "").startswith(("phase8-", "phase8_")):
        pytest.fail(
            "R1_TEST_POSTGRES_DSN must target a dedicated phase8-* or phase8_* database"
        )
    schema = "phase8-r1-" + uuid4().hex
    base = create_engine(dsn)
    with base.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = base.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        yield sessionmaker(isolated, expire_on_commit=False)
    finally:
        with base.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        base.dispose()


def test_postgres_competing_retries_commit_exactly_one_result_and_audit(pg_sessions):
    repo = SqlAlchemyOrganizationForecastRepository(pg_sessions, history_repository=None)
    operation_id = uuid4()

    def attempt(_):
        with repo.transaction(operation_id) as tx:
            cached = tx.terminal_result()
            if cached is not None:
                return cached
            return tx.finish({"status": "SUPPRESSED", "reason": "SYNTHETIC_RACE"})

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(16)))
    assert all(result == results[0] for result in results)
    assert attempt(None) == results[0]  # commit-before-ack redelivery
    with pg_sessions() as session:
        assert session.scalar(select(func.count()).select_from(SystemOperation)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_postgres_forecast_signal_points_and_audit_rollback_together(pg_sessions):
    from tests.unit.test_organization_forecast_repository import (
        test_forecast_points_signal_and_both_audits_are_one_transaction,
    )

    test_forecast_points_signal_and_both_audits_are_one_transaction(pg_sessions)


def test_postgres_running_failed_and_completed_state_transitions(pg_sessions):
    from tests.unit.test_organization_forecast_repository import (
        test_running_reservation_visible_before_computation_and_failure_is_safe,
    )

    test_running_reservation_visible_before_computation_and_failure_is_safe(pg_sessions)


def test_postgres_same_week_episode_deduplicates_competing_watermarks(pg_sessions):
    from dataclasses import replace
    from uuid import UUID

    from app.models.analytics import Forecast
    from app.models.signal import Signal
    from tests.unit.test_organization_forecast import REQUEST, configured
    from tests.unit.test_organization_forecast_repository import seed_publication

    seed_publication(pg_sessions)
    _, store, _ = configured()
    with pg_sessions.begin() as session:
        session.add(store.model)
    repo = SqlAlchemyOrganizationForecastRepository(pg_sessions, history_repository=None)

    def attempt(index):
        service, memory, _ = configured()
        watermark = f"delivery-v{index}"
        memory.input = replace(memory.input, delivery_watermark=watermark)
        result = service.run(replace(REQUEST, delivery_watermark=watermark))
        with repo.transaction(UUID(result["operation_id"])) as tx:
            cached = tx.terminal_result()
            if cached is not None:
                return cached
            return tx.finish(
                result,
                forecast=memory.forecasts[0],
                points=tuple(memory.points),
                signal=memory.signals[0],
            )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, [1, 2, 1, 2, 1, 2]))
    assert len({r["signal_id"] for r in results}) == 1
    with pg_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Forecast)) == 2
        assert session.scalar(select(func.count()).select_from(Signal)) == 1
        assert session.scalar(select(func.count()).select_from(SystemOperation)) == 2
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 3
