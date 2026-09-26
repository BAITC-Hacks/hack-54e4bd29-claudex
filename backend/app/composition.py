"""Композиционный корень.

Единственное место, где бизнес-сервисы соединяются с конкретными
реализациями хранилища. Это позволяет сохранить направление зависимости:
бизнес-слой объявляет порты, слой репозиториев их выполняет, и ни один
из них не знает о другом.

Модуль намеренно вынесен из слоёв: он собирает приложение, а не
участвует в предметной области.
"""

from __future__ import annotations

import threading
from typing import cast

from app.adapters.analytics_cache import RedisAnalyticsCache, RedisLike
from app.adapters.openai_copilot import OpenAICopilotProvider
from app.business.analytics.service import AnalyticsService
from app.business.audit.service import AuditService
from app.business.copilot.rate_limit import LocalCopilotRateLimiter
from app.business.copilot.service import CopilotService
from app.business.forecasting.service import ForecastQueryService
from app.business.hospitals.service import HospitalService
from app.business.incidents.service import IncidentService
from app.business.ingestion.query import DataImportQueryService
from app.business.ports import UnitOfWorkFactory
from app.business.regions.service import RegionService
from app.business.shared.events import EventDispatcher, get_event_dispatcher
from app.business.signals.evaluation import SignalEvaluationService
from app.business.signals.policy import SignalPolicy
from app.business.signals.ports import SignalInputRepository
from app.business.signals.service import SignalService
from app.business.simulation.service import ScenarioService
from app.core.config import AppEnv, get_settings
from app.database.clickhouse import get_client as get_clickhouse_client
from app.database.postgres import get_session_factory
from app.database.redis import get_cache_client
from app.repositories.analytics_metadata import SqlAlchemyAnalyticsMetadataRepository
from app.repositories.clickhouse_analytics import (
    ClickHouseAnalyticsRepository,
    ClickHouseQueryClient,
)
from app.repositories.clickhouse_forecasting import (
    ClickHouseQueryClient as ForecastClickHouseQueryClient,
)
from app.repositories.clickhouse_forecasting import (
    ClickHouseReferralHistoryRepository,
)
from app.repositories.forecast_metadata import SqlAlchemyForecastMetadataRepository
from app.repositories.signal_inputs import (
    ClickHouseQueryClient as SignalClickHouseQueryClient,
)
from app.repositories.signal_inputs import SqlClickHouseSignalInputRepository
from app.repositories.unit_of_work import create_unit_of_work
from app.security.authorization import AuthorizationService, get_authorization_service


def get_unit_of_work_factory() -> UnitOfWorkFactory:
    return cast(UnitOfWorkFactory, create_unit_of_work)


def _dependencies() -> tuple[UnitOfWorkFactory, AuthorizationService, EventDispatcher]:
    return (
        get_unit_of_work_factory(),
        get_authorization_service(),
        get_event_dispatcher(),
    )


def build_region_service() -> RegionService:
    uow, authz, _ = _dependencies()
    return RegionService(uow, authz)


def build_hospital_service() -> HospitalService:
    uow, authz, _ = _dependencies()
    return HospitalService(uow, authz)


def build_signal_service() -> SignalService:
    uow, authz, dispatcher = _dependencies()
    return SignalService(uow, authz, dispatcher)


_copilot_rate_limiter: LocalCopilotRateLimiter | None = None
_copilot_rate_limiter_lock = threading.Lock()


def build_copilot_service() -> CopilotService:
    global _copilot_rate_limiter
    settings = get_settings()
    if _copilot_rate_limiter is None:
        with _copilot_rate_limiter_lock:
            if _copilot_rate_limiter is None:
                _copilot_rate_limiter = LocalCopilotRateLimiter(
                    limit=settings.copilot_max_requests_per_minute
                )
    key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
    return CopilotService(
        signals=build_signal_service(),
        provider=OpenAICopilotProvider(
            api_key=key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
        ),
        enabled=settings.copilot_enabled,
        synthetic_demo_environment=settings.app_env is AppEnv.LOCAL,
        provider_name=settings.llm_provider,
        model=settings.llm_model,
        rate_limiter=_copilot_rate_limiter,
    )


def build_signal_evaluation_service() -> SignalEvaluationService:
    settings = get_settings()
    policy = SignalPolicy(
        rule_version=settings.signal_rule_version,
        freshness_max_age_hours={
            "REFERRALS": settings.signal_referrals_max_age_hours,
            "REFUSALS": settings.signal_refusals_max_age_hours,
            "WAITING": settings.signal_waiting_max_age_hours,
            "TREATED": settings.signal_treated_max_age_hours,
        },
        spike_window_days=settings.signal_spike_window_days,
        spike_reference_windows=settings.signal_spike_reference_windows,
        warning_percent=settings.signal_warning_percent,
        high_percent=settings.signal_high_percent,
        critical_percent=settings.signal_critical_percent,
        quality_warning_percent=settings.signal_quality_warning_percent,
        quality_high_percent=settings.signal_quality_high_percent,
        quality_critical_percent=settings.signal_quality_critical_percent,
        freshness_high_multiplier=settings.signal_freshness_high_multiplier,
        freshness_critical_multiplier=settings.signal_freshness_critical_multiplier,
    )
    inputs = SqlClickHouseSignalInputRepository(
        cast(SignalClickHouseQueryClient, get_clickhouse_client()),
        get_session_factory(),
    )
    return SignalEvaluationService(
        uow_factory=get_unit_of_work_factory(),
        inputs=cast(SignalInputRepository, inputs),
        policy=policy,
    )


def build_incident_service() -> IncidentService:
    uow, authz, _ = _dependencies()
    return IncidentService(uow, authz)


def build_audit_service() -> AuditService:
    uow, authz, _ = _dependencies()
    return AuditService(uow, authz)


def build_data_import_query_service() -> DataImportQueryService:
    """Чтение истории загрузок.

    Запуск импорта собирается отдельно, в `app.adapters.composition`:
    он требует библиотеки разбора файлов, которой в образе API нет
    и быть не должно.
    """
    uow, authz, _ = _dependencies()
    return DataImportQueryService(uow, authz)


def build_analytics_service() -> AnalyticsService:
    settings = get_settings()
    return AnalyticsService(
        repository=ClickHouseAnalyticsRepository(
            cast(ClickHouseQueryClient, get_clickhouse_client())
        ),
        metadata_repository=SqlAlchemyAnalyticsMetadataRepository(get_session_factory()),
        cache=RedisAnalyticsCache(cast(RedisLike, get_cache_client())),
        authorization=get_authorization_service(),
        min_cell_size=settings.analytics_min_cell_size,
        cache_ttl_seconds=settings.analytics_cache_ttl_seconds,
        max_date_range_days=settings.analytics_max_date_range_days,
    )


def build_forecast_query_service() -> ForecastQueryService:
    metadata = SqlAlchemyForecastMetadataRepository(get_session_factory())
    return ForecastQueryService(
        mapping_is_current=metadata.mapping_is_current,
        uow_factory=get_unit_of_work_factory(),
        history_repository=ClickHouseReferralHistoryRepository(
            cast(ForecastClickHouseQueryClient, get_clickhouse_client()),
            import_ids_provider=metadata.referral_history_import_ids,
        ),
        authorization=get_authorization_service(),
    )


def build_scenario_service() -> ScenarioService:
    metadata = SqlAlchemyForecastMetadataRepository(get_session_factory())
    return ScenarioService(
        mapping_is_current=metadata.mapping_is_current,
        current_mapping_version=metadata.current_mapping_version,
        uow_factory=get_unit_of_work_factory(),
        analytics=build_analytics_service(),
        authorization=get_authorization_service(),
    )
