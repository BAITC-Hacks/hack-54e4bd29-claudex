"""Scenario Analysis business rules and authoritative baseline resolution."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any, Protocol

from app.business.ports import UnitOfWorkFactory
from app.business.simulation.calculation import calculate_referral_inflow_change
from app.business.simulation.contracts import (
    FORMULA_VERSION,
    LIMITATIONS_VERSION,
    SCENARIO_LIMITATIONS,
    BaselineFreshnessStatus,
    ScenarioBaseline,
    ScenarioBaselineType,
    ScenarioCommand,
    ScenarioPreview,
    ScenarioScope,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.request_context import get_request_id
from app.models.analytics import Scenario
from app.models.enums import (
    AuditAction,
    AuditEntityType,
    DataScopeType,
    ForecastStatus,
    ScenarioStatus,
    ScenarioType,
)
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.permissions import Permission
from app.shared.analytics_contracts import (
    AnalyticsFilter,
    Granularity,
    OrganizationIdentity,
    TimeSeriesResult,
)
from app.shared.filters import ScenarioFilter
from app.shared.forecasting import REFERRAL_TARGET
from app.shared.pagination import Page, PageRequest


class ReferralAnalytics(Protocol):
    def referral_timeseries(
        self, context: SecurityContext, filters: AnalyticsFilter
    ) -> TimeSeriesResult: ...


class ScenarioService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        analytics: ReferralAnalytics,
        authorization: AuthorizationService,
        clock: Callable[[], datetime] | None = None,
        mapping_is_current: Callable[[str], bool] | None = None,
        current_mapping_version: Callable[[], str | None] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._analytics = analytics
        self._authz = authorization
        self._mapping_is_current = mapping_is_current
        self._current_mapping_version = current_mapping_version
        self._clock = clock or (lambda: datetime.now(UTC))

    def preview(
        self, context: SecurityContext, command: ScenarioCommand
    ) -> ScenarioPreview:
        self._authz.require_permission(context, Permission.SCENARIO_CREATE)
        self._validate_command_scope(context, command.scope)
        self._validate_sources(context, command)
        baseline = self._resolve_baseline(context, command)
        return self._preview(command, baseline)

    def create(
        self,
        context: SecurityContext,
        command: ScenarioCommand,
        client_request_id: uuid.UUID,
    ) -> Scenario:
        self._authz.require_permission(context, Permission.SCENARIO_CREATE)
        fingerprint = self._fingerprint(command)
        with self._uow_factory() as uow:
            existing = uow.scenarios.find_by_request(context.actor_id, client_request_id)
            if existing is not None:
                if uow.scenarios.get(existing.id, context.scope) is None:
                    raise NotFoundError("Сценарий не найден")
                self._check_mapping(context, existing.data_watermark)
                if existing.parameters.get("request_fingerprint") != fingerprint:
                    raise ConflictError(
                        "client_request_id уже использован для другого сценария"
                    )
                return existing

        # Save deliberately repeats every read performed by preview. The preview
        # result is never authoritative and may be stale by the time Save arrives.
        self._validate_command_scope(context, command.scope)
        self._validate_sources(context, command)
        baseline = self._resolve_baseline(context, command)
        self._check_mapping(context, baseline.data_watermark)
        preview = self._preview(command, baseline)
        scenario = self._to_model(
            context, command, preview, client_request_id, fingerprint
        )

        with self._uow_factory() as uow:
            if not context.has_global_scope:
                # Serialize with mapping revocation through persistence (ADR-0019).
                uow.mappings.lock()
                self._check_mapping(context, baseline.data_watermark)
            persisted, created = uow.scenarios.add_if_absent(scenario)
            if not created:
                if uow.scenarios.get(persisted.id, context.scope) is None:
                    raise NotFoundError("Сценарий не найден")
                self._check_mapping(context, persisted.data_watermark)
                if persisted.parameters.get("request_fingerprint") != fingerprint:
                    raise ConflictError(
                        "client_request_id уже использован для другого сценария"
                    )
                return persisted
            uow.audit.append(
                actor_user_id=context.actor_id,
                action=AuditAction.SCENARIO_CREATED,
                entity_type=AuditEntityType.SCENARIO,
                entity_id=persisted.id,
                request_id=get_request_id(),
                metadata={
                    "scenario_type": persisted.scenario_type.value,
                    "scope_type": persisted.scope_type.value,
                    "baseline_type": persisted.baseline_type.value,
                    "assumption_value": str(persisted.assumption_value),
                },
            )
            uow.commit()
        return persisted

    def get(self, context: SecurityContext, scenario_id: uuid.UUID) -> Scenario:
        self._authz.require_permission(context, Permission.SCENARIO_READ)
        with self._uow_factory() as uow:
            scenario = uow.scenarios.get(scenario_id, context.scope)
            if scenario is None:
                raise NotFoundError("Сценарий не найден")
        self._check_mapping(context, scenario.data_watermark)
        return scenario

    def list(
        self,
        context: SecurityContext,
        filters: ScenarioFilter,
        page: PageRequest,
    ) -> Page[Scenario]:
        self._authz.require_permission(context, Permission.SCENARIO_READ)
        if context.has_global_scope:
            with self._uow_factory() as uow:
                items, total = uow.scenarios.list(context.scope, filters, page)
            return Page.build(items, total, page)

        version = (
            self._current_mapping_version() if self._current_mapping_version else None
        )
        watermark = {"mapping_version": version}
        self._check_mapping(context, watermark)
        # Restrict both SQL count and page to the same verified mapping snapshot.
        filters = replace(filters, mapping_version=version)
        with self._uow_factory() as uow:
            items, total = uow.scenarios.list(context.scope, filters, page)
        # Revocation during the read invalidates totals as well as returned rows.
        self._check_mapping(context, watermark)
        return Page.build(items, total, page)

    def _mapping_allows(
        self, context: SecurityContext, watermark: dict[str, Any] | None
    ) -> bool:
        if context.has_global_scope:
            return True
        version = (watermark or {}).get("mapping_version")
        return (
            isinstance(version, str)
            and bool(version)
            and self._mapping_is_current is not None
            and self._mapping_is_current(version)
        )

    def _check_mapping(
        self, context: SecurityContext, watermark: dict[str, Any] | None
    ) -> None:
        if not self._mapping_allows(context, watermark):
            raise NotFoundError("Объект не найден")

    def _validate_command_scope(
        self, context: SecurityContext, scope: ScenarioScope
    ) -> None:
        if scope.scope_type is DataScopeType.GLOBAL:
            if scope.region_id is not None or scope.hospital_id is not None:
                raise ValidationError("GLOBAL scope не принимает region_id/hospital_id")
            if not context.has_global_scope:
                raise NotFoundError("Объект не найден")
            return
        if scope.scope_type is DataScopeType.REGION:
            if scope.region_id is None or scope.hospital_id is not None:
                raise ValidationError("REGION scope требует только region_id")
            self._authz.require_region_access(context, scope.region_id)
            return
        if scope.hospital_id is None or scope.region_id is not None:
            raise ValidationError("HOSPITAL scope требует только hospital_id")
        with self._uow_factory() as uow:
            hospital = uow.hospitals.get(scope.hospital_id, context.scope)
            if hospital is None:
                raise NotFoundError("Объект не найден")

    def _validate_sources(
        self, context: SecurityContext, command: ScenarioCommand
    ) -> None:
        with self._uow_factory() as uow:
            signal = None
            if command.source_signal_id is not None:
                signal = uow.signals.get(command.source_signal_id, context.scope)
                if signal is None or not self._same_scope(signal, command.scope):
                    raise NotFoundError("Сигнал не найден")
            if command.source_incident_id is not None:
                incident = uow.incidents.get(command.source_incident_id, context.scope)
                if incident is None or not self._same_scope(incident, command.scope):
                    raise NotFoundError("Инцидент не найден")
                if signal is not None and signal.incident_id != incident.id:
                    raise ValidationError("Сигнал не относится к указанному инциденту")

    @staticmethod
    def _same_scope(entity: Any, scope: ScenarioScope) -> bool:
        return (
            entity.scope_type == scope.scope_type
            and entity.region_id == scope.region_id
            and entity.hospital_id == scope.hospital_id
        )

    def _resolve_baseline(
        self, context: SecurityContext, command: ScenarioCommand
    ) -> ScenarioBaseline:
        if command.scenario_type is not ScenarioType.REFERRAL_INFLOW_CHANGE:
            raise ValidationError("Неподдерживаемый тип сценария")
        if command.baseline_type is ScenarioBaselineType.OBSERVED:
            return self._observed_baseline(context, command)
        return self._forecast_baseline(context, command)

    def _observed_baseline(
        self, context: SecurityContext, command: ScenarioCommand
    ) -> ScenarioBaseline:
        if command.period_start is None or command.period_end is None:
            raise ValidationError("Observed baseline требует период")
        if command.forecast_id is not None:
            raise ValidationError("Observed baseline не принимает forecast_id")
        if command.period_start > command.period_end:
            raise ValidationError("Начало периода не может быть позже конца")

        filters = AnalyticsFilter(
            date_from=datetime.combine(command.period_start, time.min, tzinfo=UTC),
            date_to=datetime.combine(command.period_end, time.max, tzinfo=UTC),
            granularity=Granularity.DAY,
            region_ids=(command.scope.region_id,)
            if command.scope.region_id is not None
            else (),
            organization_ids=(OrganizationIdentity.canonical(command.scope.hospital_id),)
            if command.scope.hospital_id is not None
            else (),
        )
        result = self._analytics.referral_timeseries(context, filters)
        values = [
            Decimal(str(point.value.value))
            for point in result.points
            if not point.value.suppressed and point.value.value is not None
        ]
        total = sum(values, start=Decimal("0"))
        if not values or total <= 0:
            raise NotFoundError("Baseline не найден")
        metadata = result.metadata
        if metadata.completed_import_watermark is None or not metadata.latest_import_ids:
            raise ValidationError("Observed baseline не содержит provenance")
        stale = command.period_end < self._clock().date()
        return ScenarioBaseline(
            baseline_type=ScenarioBaselineType.OBSERVED,
            value=total,
            period_start=command.period_start,
            period_end=command.period_end,
            data_watermark={
                "completed_import_watermark": (
                    metadata.completed_import_watermark.isoformat()
                ),
                "latest_import_ids": list(metadata.latest_import_ids),
                "mapping_version": metadata.mapping_version,
            },
            sources=metadata.sources,
            limitations=metadata.limitations,
            freshness_status=(
                BaselineFreshnessStatus.STALE
                if stale
                else BaselineFreshnessStatus.CURRENT
            ),
        )

    def _forecast_baseline(
        self, context: SecurityContext, command: ScenarioCommand
    ) -> ScenarioBaseline:
        if command.forecast_id is None:
            raise ValidationError("Forecast baseline требует forecast_id")
        if command.period_start is not None or command.period_end is not None:
            raise ValidationError("Forecast baseline получает период из Forecast")
        with self._uow_factory() as uow:
            forecast = uow.forecasts.get(command.forecast_id, context.scope)
            if forecast is None or not self._same_scope(forecast, command.scope):
                raise NotFoundError("Прогноз не найден")
        self._check_mapping(context, forecast.dataset_watermark)
        forecast_status = ForecastStatus(forecast.status)
        if forecast_status is not ForecastStatus.VALID:
            raise ValidationError("Прогноз не является структурно валидным")
        if forecast.target != REFERRAL_TARGET:
            raise ValidationError("Прогноз имеет неподдерживаемую цель")
        if (
            forecast.forecast_start is None
            or forecast.forecast_end is None
            or not forecast.dataset_watermark
        ):
            raise ValidationError("Прогноз не содержит полной provenance")
        stale = forecast.forecast_end < self._clock().date()
        if stale and not command.historical_analysis:
            raise ValidationError(
                "STALE forecast разрешён только для исторического сценарного анализа"
            )
        limitations = tuple(forecast.assumptions)
        if stale:
            limitations = (
                *limitations,
                "Исторический сценарий использует временно устаревший Forecast.",
            )
        return ScenarioBaseline(
            baseline_type=ScenarioBaselineType.FORECAST,
            value=Decimal(str(forecast.predicted_value)),
            period_start=forecast.forecast_start,
            period_end=forecast.forecast_end,
            data_watermark=dict(forecast.dataset_watermark),
            sources=("PERSISTED_FORECAST",),
            limitations=limitations,
            freshness_status=(
                BaselineFreshnessStatus.STALE
                if stale
                else BaselineFreshnessStatus.CURRENT
            ),
            forecast_id=forecast.id,
            model_version=forecast.model_version,
            forecast_status=forecast_status,
            selected_model=forecast.selected_model,
            forecast_generated_at=forecast.generated_at,
        )

    def _preview(
        self, command: ScenarioCommand, baseline: ScenarioBaseline
    ) -> ScenarioPreview:
        calculation = calculate_referral_inflow_change(
            baseline.value, command.assumption_value
        )
        return ScenarioPreview(
            scenario_type=command.scenario_type,
            scope=command.scope,
            baseline=baseline,
            calculation=calculation,
            formula_version=FORMULA_VERSION,
            limitations_version=LIMITATIONS_VERSION,
            historical=baseline.freshness_status is BaselineFreshnessStatus.STALE,
        )

    def _to_model(
        self,
        context: SecurityContext,
        command: ScenarioCommand,
        preview: ScenarioPreview,
        client_request_id: uuid.UUID,
        fingerprint: str,
    ) -> Scenario:
        baseline = preview.baseline
        calculation = preview.calculation
        limitations = [*baseline.limitations, *SCENARIO_LIMITATIONS]
        return Scenario(
            id=uuid.uuid4(),
            scenario_type=command.scenario_type,
            scope_type=command.scope.scope_type,
            region_id=command.scope.region_id,
            hospital_id=command.scope.hospital_id,
            created_by=context.actor_id,
            source_signal_id=command.source_signal_id,
            source_incident_id=command.source_incident_id,
            baseline_type=baseline.baseline_type,
            baseline_value=calculation.baseline_value,
            baseline_period_start=baseline.period_start,
            baseline_period_end=baseline.period_end,
            assumption_value=calculation.assumption_value,
            calculated_value=calculation.calculated_value,
            delta_absolute=calculation.delta_absolute,
            delta_percent=calculation.delta_percent,
            data_watermark=baseline.data_watermark,
            forecast_id=baseline.forecast_id,
            model_version=baseline.model_version,
            forecast_status=baseline.forecast_status,
            baseline_freshness_status=baseline.freshness_status,
            parameters={
                "request_fingerprint": fingerprint,
                "sources": list(baseline.sources),
                "selected_model": baseline.selected_model,
                "forecast_generated_at": baseline.forecast_generated_at.isoformat()
                if baseline.forecast_generated_at
                else None,
            },
            limitations_snapshot=limitations,
            formula_version=preview.formula_version,
            limitations_version=preview.limitations_version,
            client_request_id=client_request_id,
            status=ScenarioStatus.COMPLETED,
            created_at=self._clock(),
        )

    @staticmethod
    def _fingerprint(command: ScenarioCommand) -> str:
        payload = {
            "scenario_type": command.scenario_type.value,
            "scope_type": command.scope.scope_type.value,
            "region_id": (
                str(command.scope.region_id) if command.scope.region_id else None
            ),
            "hospital_id": str(command.scope.hospital_id)
            if command.scope.hospital_id
            else None,
            "baseline_type": command.baseline_type.value,
            "assumption_value": str(command.assumption_value),
            "period_start": command.period_start.isoformat()
            if command.period_start
            else None,
            "period_end": command.period_end.isoformat() if command.period_end else None,
            "forecast_id": str(command.forecast_id) if command.forecast_id else None,
            "historical_analysis": command.historical_analysis,
            "source_signal_id": str(command.source_signal_id)
            if command.source_signal_id
            else None,
            "source_incident_id": str(command.source_incident_id)
            if command.source_incident_id
            else None,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


__all__ = ["ScenarioService"]
