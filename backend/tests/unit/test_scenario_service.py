from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.business.simulation.contracts import (
    BaselineFreshnessStatus,
    ScenarioBaselineType,
    ScenarioCommand,
    ScenarioScope,
)
from app.business.simulation.service import ScenarioService
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.analytics import Forecast
from app.models.enums import (
    AuditAction,
    DataScopeType,
    ForecastStatus,
    ScenarioType,
)
from app.models.incident import Incident
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role
from app.shared.analytics_contracts import (
    AnalyticsCell,
    AnalyticsMetadata,
    Granularity,
    MetricName,
    TimeSeriesPoint,
    TimeSeriesResult,
)
from app.shared.filters import ScenarioFilter
from app.shared.pagination import PageRequest
from tests.fakes import (
    FakeMappingRepository,
    FakeScenarioRepository,
    FakeStore,
    FakeUnitOfWork,
    make_context,
    make_hospital,
    make_region,
    make_signal,
    make_user,
    unit_of_work_factory,
)


class StubAnalytics:
    def __init__(self, value: int = 100) -> None:
        self.value = value
        self.calls = 0
        self.last_filters = None

    def referral_timeseries(self, context, filters) -> TimeSeriesResult:
        _ = context
        self.calls += 1
        self.last_filters = filters
        return TimeSeriesResult(
            metadata=AnalyticsMetadata(
                date_from=filters.date_from,
                date_to=filters.date_to,
                sources=("ИС БГ:REFERRALS",),
                generated_at=datetime(2025, 4, 1, tzinfo=UTC),
                completed_import_watermark=datetime(2025, 3, 31, tzinfo=UTC),
                limitations=("Hospital mapping incomplete.",),
                granularity=Granularity.DAY,
                latest_import_ids=("import-1",),
                mapping_version="mapping-v1",
            ),
            metric=MetricName.REFERRALS_TOTAL,
            points=(
                TimeSeriesPoint(
                    filters.date_from,
                    filters.date_to,
                    AnalyticsCell(value=self.value, suppressed=False),
                ),
            ),
        )


def _service(
    store: FakeStore,
    analytics: StubAnalytics,
    mapping_is_current: Callable[[str], bool] | None = None,
    current_mapping_version: Callable[[], str | None] | None = lambda: "mapping-v1",
) -> ScenarioService:
    return ScenarioService(
        uow_factory=unit_of_work_factory(store),
        analytics=analytics,
        authorization=AuthorizationService(),
        mapping_is_current=mapping_is_current,
        current_mapping_version=current_mapping_version,
        clock=lambda: datetime(2026, 9, 17, tzinfo=UTC),
    )


def _observed_command() -> ScenarioCommand:
    return ScenarioCommand(
        scenario_type=ScenarioType.REFERRAL_INFLOW_CHANGE,
        scope=ScenarioScope(DataScopeType.GLOBAL),
        baseline_type=ScenarioBaselineType.OBSERVED,
        assumption_value=Decimal("0.20"),
        period_start=date(2025, 1, 1),
        period_end=date(2025, 3, 31),
        historical_analysis=True,
    )


def _forecast(actor_id: uuid.UUID) -> Forecast:
    _ = actor_id
    return Forecast(
        id=uuid.uuid4(),
        hospital_id=None,
        region_id=None,
        scope_type=DataScopeType.GLOBAL,
        target="DAILY_REFERRAL_COUNT",
        horizon_days=7,
        predicted_value=Decimal("56837.0000"),
        model_version="referrals-global-v1",
        input_period_start=datetime(2025, 1, 1, tzinfo=UTC),
        input_period_end=datetime(2025, 3, 31, tzinfo=UTC),
        generated_at=datetime(2025, 4, 1, tzinfo=UTC),
        status=ForecastStatus.VALID,
        assumptions=[],
        selected_model="weekly_naive",
        baseline_model="weekly_naive",
        feature_schema_version="v1",
        dataset_watermark={"latest_import_id": "import-1"},
        validation_metrics={},
        baseline_metrics={},
        validation_folds=[],
        forecast_start=date(2025, 4, 1),
        forecast_end=date(2025, 4, 7),
    )


def test_observed_preview_gets_authoritative_baseline_without_persistence() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=actor)
    analytics = StubAnalytics(100)

    result = _service(store, analytics).preview(context, _observed_command())

    assert result.calculation.baseline_value == Decimal("100.0000")
    assert result.calculation.calculated_value == Decimal("120.0000")
    assert result.baseline.freshness_status is BaselineFreshnessStatus.STALE
    assert result.historical is True
    assert store.scenarios == {}
    assert store.audit == []


def test_create_reacquires_baseline_and_writes_scenario_and_audit_once() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=actor)
    analytics = StubAnalytics(100)
    service = _service(store, analytics)
    request_id = uuid.uuid4()

    created = service.create(context, _observed_command(), request_id)
    retried = service.create(context, _observed_command(), request_id)

    assert created.id == retried.id
    assert analytics.calls == 1
    assert len(store.scenarios) == 1
    assert [event.action for event in store.audit] == [AuditAction.SCENARIO_CREATED]
    assert store.commits == 1


def test_same_idempotency_key_with_different_request_is_conflict() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=actor)
    service = _service(store, StubAnalytics())
    request_id = uuid.uuid4()
    service.create(context, _observed_command(), request_id)
    changed = replace(_observed_command(), assumption_value=Decimal("0.10"))

    with pytest.raises(ConflictError):
        service.create(context, changed, request_id)


def test_stale_valid_forecast_requires_historical_opt_in_and_keeps_both_states() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=actor)
    forecast = _forecast(actor.id)
    store.forecasts[forecast.id] = forecast
    service = _service(store, StubAnalytics())
    command = ScenarioCommand(
        scenario_type=ScenarioType.REFERRAL_INFLOW_CHANGE,
        scope=ScenarioScope(DataScopeType.GLOBAL),
        baseline_type=ScenarioBaselineType.FORECAST,
        assumption_value=Decimal("0.20"),
        forecast_id=forecast.id,
        historical_analysis=False,
    )

    with pytest.raises(ValidationError, match="исторического"):
        service.preview(context, command)

    historical = ScenarioCommand(
        scenario_type=command.scenario_type,
        scope=command.scope,
        baseline_type=command.baseline_type,
        assumption_value=command.assumption_value,
        forecast_id=command.forecast_id,
        historical_analysis=True,
    )
    result = service.preview(context, historical)

    assert result.baseline.forecast_status is ForecastStatus.VALID
    assert result.baseline.freshness_status is BaselineFreshnessStatus.STALE
    assert result.baseline.model_version == "referrals-global-v1"
    assert result.calculation.calculated_value == Decimal("68204.4000")


def test_restricted_user_cannot_create_global_scenario() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(
        roles={Role.REGIONAL_ANALYST},
        scope=DataScope(region_ids=frozenset({str(uuid.uuid4())}), resolved=True),
        user=actor,
    )

    with pytest.raises(NotFoundError):
        _service(store, StubAnalytics()).preview(context, _observed_command())


def test_source_signal_is_preserved_without_mutating_signal() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=actor)
    region = store.add_region(make_region())
    hospital = store.add_hospital(make_hospital(region))
    signal = make_signal(hospital)
    signal.scope_type = DataScopeType.GLOBAL
    signal.hospital_id = None
    signal.region_id = None
    store.add_signal(signal)
    original_version = signal.version
    command = replace(_observed_command(), source_signal_id=signal.id)

    scenario = _service(store, StubAnalytics()).create(context, command, uuid.uuid4())

    assert scenario.source_signal_id == signal.id
    assert signal.version == original_version
    assert signal.incident_id is None


def test_new_intentional_save_creates_new_immutable_history_item() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=actor)
    service = _service(store, StubAnalytics())

    first = service.create(context, _observed_command(), uuid.uuid4())
    second = service.create(context, _observed_command(), uuid.uuid4())

    assert first.id != second.id
    assert len(store.scenarios) == 2
    assert len(store.audit) == 2


def test_region_and_hospital_scopes_are_sent_to_authoritative_analytics() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    region = store.add_region(make_region())
    hospital = store.add_hospital(make_hospital(region))
    analytics = StubAnalytics()
    service = _service(store, analytics)
    region_context = make_context(
        roles={Role.REGIONAL_ANALYST},
        scope=DataScope(region_ids=frozenset({str(region.id)}), resolved=True),
        user=actor,
    )
    service.preview(
        region_context,
        replace(
            _observed_command(),
            scope=ScenarioScope(DataScopeType.REGION, region_id=region.id),
        ),
    )
    assert analytics.last_filters.region_ids == (region.id,)

    hospital_context = make_context(
        roles={Role.HOSPITAL_ANALYST},
        scope=DataScope(hospital_ids=frozenset({str(hospital.id)}), resolved=True),
        user=actor,
    )
    service.preview(
        hospital_context,
        replace(
            _observed_command(),
            scope=ScenarioScope(DataScopeType.HOSPITAL, hospital_id=hospital.id),
        ),
    )
    assert analytics.last_filters.organization_ids[0].key == f"canonical:{hospital.id}"


def test_signal_and_incident_links_require_same_scope_and_do_not_mutate_sources() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=actor)
    region = store.add_region(make_region())
    hospital = store.add_hospital(make_hospital(region))
    signal = make_signal(hospital)
    signal.scope_type = DataScopeType.GLOBAL
    signal.hospital_id = None
    signal.region_id = None
    incident = Incident(
        id=uuid.uuid4(),
        scope_type=DataScopeType.GLOBAL,
        region_id=None,
        hospital_id=None,
        title="Synthetic global incident",
        status="OPEN",
        created_by=actor.id,
        version=1,
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
        updated_at=datetime(2026, 9, 17, tzinfo=UTC),
    )
    signal.incident_id = incident.id
    store.add_signal(signal)
    store.incidents[incident.id] = incident
    command = replace(
        _observed_command(),
        source_signal_id=signal.id,
        source_incident_id=incident.id,
    )

    scenario = _service(store, StubAnalytics()).create(context, command, uuid.uuid4())

    assert scenario.source_signal_id == signal.id
    assert scenario.source_incident_id == incident.id
    assert incident.status == "OPEN"
    assert incident.version == 1


def _regional_context(store: FakeStore):
    actor = store.add_user(make_user())
    region = store.add_region(make_region())
    context = make_context(
        roles={Role.REGIONAL_ANALYST},
        scope=DataScope(region_ids=frozenset({str(region.id)}), resolved=True),
        user=actor,
    )
    return context, ScenarioScope(DataScopeType.REGION, region_id=region.id)


@pytest.mark.parametrize("operation", ["preview", "create"])
def test_restricted_forecast_fails_closed_without_mapping_validator(operation) -> None:
    store = FakeStore()
    context, scope = _regional_context(store)
    forecast = _forecast(context.actor_id)
    forecast.scope_type = scope.scope_type
    forecast.region_id = scope.region_id
    forecast.dataset_watermark["mapping_version"] = "mapping-v1"
    store.forecasts[forecast.id] = forecast
    command = ScenarioCommand(
        scenario_type=ScenarioType.REFERRAL_INFLOW_CHANGE,
        scope=scope,
        baseline_type=ScenarioBaselineType.FORECAST,
        assumption_value=Decimal("0.20"),
        forecast_id=forecast.id,
        historical_analysis=True,
    )
    service = _service(store, StubAnalytics())

    with pytest.raises(NotFoundError):
        if operation == "preview":
            service.preview(context, command)
        else:
            service.create(context, command, uuid.uuid4())
    assert store.scenarios == {}
    assert store.audit == []


def test_observed_scenario_persists_mapping_version_from_analytics() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=actor)
    scenario = _service(store, StubAnalytics()).create(
        context, _observed_command(), uuid.uuid4()
    )
    assert scenario.data_watermark["mapping_version"] == "mapping-v1"


@pytest.mark.parametrize("operation", ["get", "retry", "changed_retry", "list"])
def test_saved_scenario_fails_closed_without_mapping_validator(operation) -> None:
    store = FakeStore()
    context, scope = _regional_context(store)
    global_context = replace(
        context, roles=frozenset({Role.ADMIN}), scope=DataScope.global_scope()
    )
    command = replace(_observed_command(), scope=scope)
    service = _service(store, StubAnalytics())
    request_id = uuid.uuid4()
    saved = service.create(global_context, command, request_id)

    if operation == "list":
        with pytest.raises(NotFoundError):
            service.list(context, ScenarioFilter(), PageRequest())
    else:
        with pytest.raises(NotFoundError):
            if operation == "get":
                service.get(context, saved.id)
            else:
                if operation == "changed_retry":
                    command = replace(command, assumption_value=Decimal("0.10"))
                service.create(context, command, request_id)
    assert len(store.scenarios) == 1
    assert len(store.audit) == 1


@pytest.mark.parametrize("scope_type", [DataScopeType.REGION, DataScopeType.HOSPITAL])
@pytest.mark.parametrize("version", ["mapping-v1", "revoked", None, "", 123])
def test_forecast_mapping_guard_for_restricted_scopes(scope_type, version) -> None:
    store = FakeStore()
    context, scope = _regional_context(store)
    if scope_type is DataScopeType.HOSPITAL:
        region = store.regions[scope.region_id]
        hospital = store.add_hospital(make_hospital(region))
        scope = ScenarioScope(DataScopeType.HOSPITAL, hospital_id=hospital.id)
        context = replace(
            context,
            roles=frozenset({Role.HOSPITAL_ANALYST}),
            scope=DataScope(hospital_ids=frozenset({str(hospital.id)}), resolved=True),
        )
    forecast = _forecast(context.actor_id)
    forecast.scope_type = scope.scope_type
    forecast.region_id = scope.region_id
    forecast.hospital_id = scope.hospital_id
    forecast.dataset_watermark["mapping_version"] = version
    store.forecasts[forecast.id] = forecast
    command = ScenarioCommand(
        scenario_type=ScenarioType.REFERRAL_INFLOW_CHANGE,
        scope=scope,
        baseline_type=ScenarioBaselineType.FORECAST,
        assumption_value=Decimal("0.20"),
        forecast_id=forecast.id,
        historical_analysis=True,
    )
    service = _service(store, StubAnalytics(), lambda value: value == "mapping-v1")
    if version == "mapping-v1":
        result = service.preview(context, command)
        assert result.baseline.value == Decimal("56837.0000")
        assert result.baseline.data_watermark["mapping_version"] == "mapping-v1"
        assert result.historical is True
        saved = service.create(context, command, uuid.uuid4())
        assert saved.baseline_value == Decimal("56837.0000")
    else:
        with pytest.raises(NotFoundError):
            service.preview(context, command)
        with pytest.raises(NotFoundError):
            service.create(context, command, uuid.uuid4())
        assert store.scenarios == {}


@pytest.mark.parametrize("version", ["revoked", None, "", 123])
def test_saved_mapping_guard_blocks_restricted_reads_but_not_global(
    version,
) -> None:
    store = FakeStore()
    context, scope = _regional_context(store)
    current_versions = {"mapping-v1"}
    service = _service(store, StubAnalytics(), current_versions.__contains__)
    command = replace(_observed_command(), scope=scope)
    request_id = uuid.uuid4()
    saved = service.create(context, command, request_id)
    assert service.get(context, saved.id).id == saved.id
    assert service.create(context, command, request_id).id == saved.id
    # Model a legacy record (no mapping version) as well as revoked provenance.
    saved.data_watermark = {**saved.data_watermark, "mapping_version": version}
    with pytest.raises(NotFoundError):
        service.get(context, saved.id)
    with pytest.raises(NotFoundError):
        service.create(context, command, request_id)
    with pytest.raises(NotFoundError):
        service.create(
            context, replace(command, assumption_value=Decimal("0.10")), request_id
        )
    listed = service.list(context, ScenarioFilter(), PageRequest())
    assert listed.items == []
    assert listed.total == 0

    global_context = replace(
        context, roles=frozenset({Role.ADMIN}), scope=DataScope.global_scope()
    )
    assert service.get(global_context, saved.id).id == saved.id
    assert service.create(global_context, command, request_id).id == saved.id
    global_page = service.list(global_context, ScenarioFilter(), PageRequest())
    assert [item.id for item in global_page.items] == [saved.id]
    assert global_page.total == 1
    assert len(store.audit) == 1


def test_mapping_revocation_after_save_hides_unchanged_snapshot() -> None:
    store = FakeStore()
    context, scope = _regional_context(store)
    current_versions = {"mapping-v1"}
    service = _service(store, StubAnalytics(), current_versions.__contains__)
    command = replace(_observed_command(), scope=scope)
    saved = service.create(context, command, uuid.uuid4())
    current_versions.clear()
    with pytest.raises(NotFoundError):
        service.get(context, saved.id)
    with pytest.raises(NotFoundError):
        service.create(context, command, saved.client_request_id)
    with pytest.raises(NotFoundError):
        service.list(context, ScenarioFilter(), PageRequest())
    assert saved.data_watermark["mapping_version"] == "mapping-v1"
    assert saved.baseline_value == Decimal("100.0000")


@pytest.mark.parametrize("sort_desc", [False, True])
def test_restricted_list_filters_before_pagination_and_counts(
    sort_desc, monkeypatch
) -> None:
    store = FakeStore()
    context, scope = _regional_context(store)
    global_context = replace(
        context, roles=frozenset({Role.ADMIN}), scope=DataScope.global_scope()
    )
    service = _service(store, StubAnalytics(), lambda value: value == "mapping-v1")
    command = replace(_observed_command(), scope=scope)
    visible = []

    # More than one repository batch, with revoked and legacy rows between hits.
    for index in range(105):
        saved = service.create(global_context, command, uuid.uuid4())
        saved.created_at += timedelta(seconds=index)
        if index in (1, 51, 103):
            visible.append(saved.id)
        else:
            saved.data_watermark = {"mapping_version": "revoked"} if index % 2 else {}
    ordered = list(reversed(visible)) if sort_desc else visible
    original_list = FakeScenarioRepository.list
    requests = []

    def tracked_list(self, scope, filters, page):
        requests.append(page)
        return original_list(self, scope, filters, page)

    monkeypatch.setattr(FakeScenarioRepository, "list", tracked_list)
    for number, expected in [(1, ordered[:2]), (2, ordered[2:]), (3, [])]:
        page = service.list(
            context,
            ScenarioFilter(),
            PageRequest(
                page=number, page_size=2, sort_by="created_at", sort_desc=sort_desc
            ),
        )
        assert [item.id for item in page.items] == expected
        assert page.total == 3
        assert page.has_next is (number == 1)
        assert len(requests) == number
        assert requests[-1].page == number
        assert requests[-1].page_size == 2
    empty = service.list(
        context, ScenarioFilter(source_signal_id=uuid.uuid4()), PageRequest()
    )
    assert empty.items == []
    assert empty.total == 0


@pytest.mark.parametrize("reason", ["revoked", "out_of_scope"])
def test_idempotency_race_rechecks_winner_visibility(monkeypatch, reason) -> None:
    store = FakeStore()
    context, scope = _regional_context(store)
    global_context = replace(
        context, roles=frozenset({Role.ADMIN}), scope=DataScope.global_scope()
    )
    service = _service(store, StubAnalytics(), lambda value: value == "mapping-v1")
    command = replace(_observed_command(), scope=scope)
    request_id = uuid.uuid4()
    winner = service.create(global_context, command, request_id)
    store.scenarios.clear()
    if reason == "revoked":
        winner.data_watermark = {"mapping_version": "revoked"}
    else:
        winner.region_id = uuid.uuid4()

    def concurrent_insert(self, scenario):
        _ = self, scenario
        store.scenarios[winner.id] = winner
        return winner, False

    monkeypatch.setattr(FakeScenarioRepository, "add_if_absent", concurrent_insert)
    with pytest.raises(NotFoundError):
        service.create(context, command, request_id)
    assert len(store.audit) == 1


def test_global_historical_forecast_ignores_mapping_revocation() -> None:
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=actor)
    forecast = _forecast(actor.id)
    forecast.dataset_watermark["mapping_version"] = "revoked"
    store.forecasts[forecast.id] = forecast
    command = ScenarioCommand(
        scenario_type=ScenarioType.REFERRAL_INFLOW_CHANGE,
        scope=ScenarioScope(DataScopeType.GLOBAL),
        baseline_type=ScenarioBaselineType.FORECAST,
        assumption_value=Decimal("0.20"),
        forecast_id=forecast.id,
        historical_analysis=True,
    )
    service = _service(store, StubAnalytics(), lambda _version: False)
    assert service.preview(context, command).historical is True
    assert service.create(context, command, uuid.uuid4()).baseline_value == Decimal(
        "56837.0000"
    )


def test_restricted_list_without_version_provider_fails_before_repository(monkeypatch):
    store = FakeStore()
    context, _ = _regional_context(store)
    service = _service(store, StubAnalytics(), lambda _version: True, None)

    def forbidden_list(*args):
        raise AssertionError("Unavailable mapping must stop before repository access")

    monkeypatch.setattr(FakeScenarioRepository, "list", forbidden_list)
    with pytest.raises(NotFoundError):
        service.list(context, ScenarioFilter(), PageRequest())


@pytest.mark.parametrize("version", [None, "", 123, "revoked"])
def test_restricted_list_rejects_unavailable_version_before_query(monkeypatch, version):
    store = FakeStore()
    context, _ = _regional_context(store)
    service = _service(
        store, StubAnalytics(), lambda value: value == "mapping-v1", lambda: version
    )

    def forbidden_list(*args):
        raise AssertionError("Unverified mapping must stop before repository access")

    monkeypatch.setattr(FakeScenarioRepository, "list", forbidden_list)
    with pytest.raises(NotFoundError):
        service.list(context, ScenarioFilter(), PageRequest())


@pytest.mark.parametrize("revoke_during_query", [False, True])
@pytest.mark.parametrize("row_count", [0, 5])
def test_list_captures_one_version_and_checks_it_before_and_after_query(
    monkeypatch, revoke_during_query, row_count
):
    store = FakeStore()
    context, scope = _regional_context(store)
    global_context = replace(
        context, roles=frozenset({Role.ADMIN}), scope=DataScope.global_scope()
    )
    seed_service = _service(store, StubAnalytics())
    for _ in range(row_count):
        seed_service.create(
            global_context, replace(_observed_command(), scope=scope), uuid.uuid4()
        )
    events = []
    current = True

    def version_provider():
        events.append("version")
        return "mapping-v1"

    def is_current(version):
        assert version == "mapping-v1"
        events.append("check")
        return current

    original_list = FakeScenarioRepository.list
    request = PageRequest(page=1, page_size=2, sort_by="created_at")
    supplied_filters = ScenarioFilter(
        scope_type=DataScopeType.REGION, mapping_version="untrusted-version"
    )

    def tracked_list(self, scope, filters, page):
        nonlocal current
        events.append("query")
        assert page == request
        assert filters.mapping_version == "mapping-v1"
        assert filters.scope_type is DataScopeType.REGION
        result = original_list(self, scope, filters, page)
        if revoke_during_query:
            current = False
        return result

    monkeypatch.setattr(FakeScenarioRepository, "list", tracked_list)
    service = _service(store, StubAnalytics(), is_current, version_provider)
    if revoke_during_query:
        with pytest.raises(NotFoundError):
            service.list(context, supplied_filters, request)
    else:
        result = service.list(context, supplied_filters, request)
        assert len(result.items) == min(row_count, 2)
        assert result.total == row_count
    assert events == ["version", "check", "query", "check"]
    assert supplied_filters.mapping_version == "untrusted-version"


def test_global_list_does_not_require_mapping_providers():
    store = FakeStore()
    context, scope = _regional_context(store)
    global_context = replace(
        context, roles=frozenset({Role.ADMIN}), scope=DataScope.global_scope()
    )

    def forbidden_provider(*args):
        raise AssertionError("Global history must remain independent of mapping state")

    service = _service(store, StubAnalytics(), forbidden_provider, forbidden_provider)
    saved = service.create(
        global_context, replace(_observed_command(), scope=scope), uuid.uuid4()
    )
    saved.data_watermark = {}
    result = service.list(global_context, ScenarioFilter(), PageRequest())
    assert [item.id for item in result.items] == [saved.id]
    assert result.total == 1


@pytest.mark.parametrize("baseline_type", list(ScenarioBaselineType))
@pytest.mark.parametrize("revoked_while_acquiring_lock", [False, True])
def test_restricted_create_locks_and_rechecks_mapping_through_commit(
    baseline_type, revoked_while_acquiring_lock
):
    store = FakeStore()
    context, scope = _regional_context(store)
    command = replace(_observed_command(), scope=scope)
    if baseline_type is ScenarioBaselineType.FORECAST:
        forecast = _forecast(context.actor_id)
        forecast.scope_type = scope.scope_type
        forecast.region_id = scope.region_id
        forecast.dataset_watermark["mapping_version"] = "mapping-v1"
        store.forecasts[forecast.id] = forecast
        command = replace(
            command,
            baseline_type=baseline_type,
            forecast_id=forecast.id,
            period_start=None,
            period_end=None,
        )
    events = []
    units = []
    current = True

    def factory():
        uow = FakeUnitOfWork(store)
        units.append(uow)
        original_lock = uow.mappings.lock
        original_insert = uow.scenarios.add_if_absent
        original_commit = uow.commit

        def lock():
            nonlocal current
            original_lock()
            events.append("lock")
            if revoked_while_acquiring_lock:
                current = False

        def insert(scenario):
            events.append(("insert", uow.mappings.locked))
            return original_insert(scenario)

        def commit():
            events.append(("commit", uow.mappings.locked))
            original_commit()

        uow.mappings.lock = lock
        uow.scenarios.add_if_absent = insert
        uow.commit = commit
        return uow

    def is_current(version):
        assert version == "mapping-v1"
        events.append(("check", any(uow.mappings.locked for uow in units)))
        return current

    service = ScenarioService(
        uow_factory=factory,
        analytics=StubAnalytics(),
        authorization=AuthorizationService(),
        mapping_is_current=is_current,
        clock=lambda: datetime(2026, 9, 17, tzinfo=UTC),
    )
    if revoked_while_acquiring_lock:
        with pytest.raises(NotFoundError):
            service.create(context, command, uuid.uuid4())
        assert events[-2:] == ["lock", ("check", True)]
        assert store.scenarios == {}
        assert store.audit == []
        assert store.commits == 0
    else:
        saved = service.create(context, command, uuid.uuid4())
        assert saved.id in store.scenarios
        assert events[-4:] == [
            "lock",
            ("check", True),
            ("insert", True),
            ("commit", True),
        ]
        assert store.commits == 1
        assert len(store.audit) == 1
    # The read guard remains, and the write lock belongs to the write UOW.
    assert events[0] == ("check", False)
    assert all(not uow.mappings.locked for uow in units)


def test_global_historical_create_does_not_take_mapping_lock(monkeypatch):
    store = FakeStore()
    actor = store.add_user(make_user())
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope(), user=actor)

    def forbidden_lock(self):
        raise AssertionError("Global historical saves do not depend on current mapping")

    monkeypatch.setattr(FakeMappingRepository, "lock", forbidden_lock)
    saved = _service(store, StubAnalytics()).create(
        context, _observed_command(), uuid.uuid4()
    )
    assert saved.id in store.scenarios
    assert store.commits == 1
