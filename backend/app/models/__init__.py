"""Модели SQLAlchemy.

Все модели импортируются здесь, чтобы Alembic видел полную схему
при сравнении с состоянием базы.
"""

from __future__ import annotations

from app.models.access import User, UserDataScope
from app.models.action import Action
from app.models.analytics import Forecast, Scenario
from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.data_import import DataImport
from app.models.delivery import Delivery, DeliveryPart
from app.models.directory import Hospital, Region
from app.models.enums import (
    ActionType,
    AuditAction,
    AuditEntityType,
    BaselineFreshnessStatus,
    DataImportStatus,
    DataScopeType,
    DatasetType,
    ExplanationGenerator,
    FactorDirection,
    ForecastStatus,
    IncidentStatus,
    MappingMethod,
    MappingStatus,
    ModelVersionStatus,
    QualitySeverity,
    ScenarioBaselineType,
    ScenarioStatus,
    ScenarioType,
    SignalClosureDisposition,
    SignalSeverity,
    SignalSourceType,
    SignalStatus,
    SignalType,
    SourceSystem,
)
from app.models.forecast_point import ForecastPoint
from app.models.incident import Incident
from app.models.mapping import (
    MappingRevision,
    MappingState,
    OrganizationAlias,
    ProfileAlias,
    RegionAlias,
)
from app.models.model_version import ModelVersion
from app.models.quality import DataQualityResult, QuarantineBatch
from app.models.signal import Signal, SignalExplanation
from app.models.system import OperationStatus, SystemOperation

__all__ = [
    "Action",
    "ActionType",
    "AuditAction",
    "AuditEntityType",
    "AuditEvent",
    "Base",
    "BaselineFreshnessStatus",
    "DataImport",
    "DataImportStatus",
    "DataQualityResult",
    "DataScopeType",
    "DatasetType",
    "Delivery",
    "DeliveryPart",
    "ExplanationGenerator",
    "FactorDirection",
    "Forecast",
    "ForecastPoint",
    "ForecastStatus",
    "Hospital",
    "Incident",
    "IncidentStatus",
    "MappingMethod",
    "MappingRevision",
    "MappingState",
    "MappingStatus",
    "ModelVersion",
    "ModelVersionStatus",
    "OperationStatus",
    "OrganizationAlias",
    "ProfileAlias",
    "QualitySeverity",
    "QuarantineBatch",
    "Region",
    "RegionAlias",
    "Scenario",
    "ScenarioBaselineType",
    "ScenarioStatus",
    "ScenarioType",
    "Signal",
    "SignalClosureDisposition",
    "SignalExplanation",
    "SignalSeverity",
    "SignalSourceType",
    "SignalStatus",
    "SignalType",
    "SourceSystem",
    "SystemOperation",
    "User",
    "UserDataScope",
]
