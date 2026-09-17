from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
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
from tests.fakes import (
    FakeStore,
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


def _service(store: FakeStore, analytics: StubAnalytics) -> ScenarioService:
    return ScenarioService(
        uow_factory=unit_of_work_factory(store),
        analytics=analytics,
        authorization=AuthorizationService(),
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
