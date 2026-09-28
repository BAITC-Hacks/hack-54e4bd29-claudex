"""Synthetic SQL execution for Scenario mapping filtering; no external services."""

import uuid
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.analytics import Scenario
from app.models.directory import Hospital
from app.repositories.analytics import SqlAlchemyScenarioRepository
from app.security.context import DataScope, Role
from app.shared.filters import ScenarioFilter
from app.shared.pagination import PageRequest
from tests.fakes import FakeScenarioRepository, FakeStore
from tests.unit.test_scenario_service import (
    StubAnalytics,
    _observed_command,
    _regional_context,
    _service,
)


@compiles(JSONB, "sqlite")
def jsonb_for_scenario_sqlite(element, compiler, **kw):
    return "JSON"


@pytest.fixture(params=["sqlite", "fake"])
def scenario_repository(request):
    store = FakeStore()
    context, scope = _regional_context(store)
    global_context = replace(
        context, roles=frozenset({Role.ADMIN}), scope=DataScope.global_scope()
    )
    service = _service(store, StubAnalytics())
    signal_id = uuid.uuid4()
    # Newest-first: wrong region, wrong source, valid, legacy, valid, revoked.
    versions = ["revoked", "mapping-v1", None, "mapping-v1", "mapping-v1", "mapping-v1"]
    expected = []
    for index, version in enumerate(versions):
        scenario = service.create(
            global_context, replace(_observed_command(), scope=scope), uuid.uuid4()
        )
        scenario.created_at += timedelta(seconds=index)
        scenario.data_watermark = {} if version is None else {"mapping_version": version}
        scenario.source_signal_id = signal_id if index != 4 else uuid.uuid4()
        if index == 5:
            scenario.region_id = uuid.uuid4()
        if index in (1, 3):
            expected.insert(0, scenario.id)
    if request.param == "fake":
        yield FakeScenarioRepository(store), context.scope, signal_id, expected, None
        return
    engine = create_engine("sqlite:///:memory:")
    Hospital.__table__.create(engine)
    Scenario.__table__.create(engine)
    statements = []
    with Session(engine) as session:
        session.add_all(store.scenarios.values())
        session.commit()

        @event.listens_for(engine, "before_cursor_execute")
        def record_statement(connection, cursor, statement, parameters, context, many):
            statements.append(statement)

        yield (
            SqlAlchemyScenarioRepository(session),
            context.scope,
            signal_id,
            expected,
            statements,
        )
    engine.dispose()


def test_mapping_filter_precedes_count_and_pagination(scenario_repository):
    repo, scope, signal_id, expected, statements = scenario_repository
    filters = ScenarioFilter(mapping_version="mapping-v1", source_signal_id=signal_id)
    for number in (1, 2, 3):
        items, total = repo.list(
            scope, filters, PageRequest(page=number, page_size=1, sort_by="created_at")
        )
        assert [item.id for item in items] == expected[number - 1 : number]
        assert total == 2
    if statements is not None:
        assert len(statements) == 6  # one count + one bounded SELECT per request
        assert all("LIMIT" in query for query in statements[1::2])
        assert all("JSON_EXTRACT" in query for query in statements)


def test_unfiltered_history_keeps_legacy_and_revoked_rows(scenario_repository):
    repo, scope, signal_id, expected, statements = scenario_repository
    items, total = repo.list(
        DataScope.global_scope(),
        ScenarioFilter(),
        PageRequest(page_size=10, sort_by="created_at"),
    )
    assert len(items) == total == 6
