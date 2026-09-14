"""Модели SQLAlchemy.

Все модели импортируются здесь, чтобы Alembic видел полную схему
при сравнении с состоянием базы.
"""

from app.models.access import User, UserDataScope
from app.models.action import Action
from app.models.analytics import Forecast, Scenario
from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.data_import import DataImport
from app.models.directory import Hospital, Region
from app.models.enums import (
    ActionType,
    AuditAction,
    AuditEntityType,
    DataImportStatus,
    DataScopeType,
    DatasetType,
    ExplanationGenerator,
    FactorDirection,
    ForecastStatus,
    IncidentStatus,
    MappingMethod,
    MappingStatus,
    QualitySeverity,
    ScenarioStatus,
    ScenarioType,
    SignalSeverity,
    SignalSourceType,
    SignalStatus,
    SignalType,
    SourceSystem,
)
from app.models.incident import Incident
from app.models.mapping import OrganizationAlias, ProfileAlias, RegionAlias
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
    "DataImport",
    "DataImportStatus",
    "DataQualityResult",
    "DataScopeType",
    "DatasetType",
    "ExplanationGenerator",
    "FactorDirection",
    "Forecast",
    "ForecastStatus",
    "Hospital",
    "Incident",
    "IncidentStatus",
    "MappingMethod",
    "MappingStatus",
    "OperationStatus",
    "OrganizationAlias",
    "ProfileAlias",
    "QualitySeverity",
    "QuarantineBatch",
    "Region",
    "RegionAlias",
    "Scenario",
    "ScenarioStatus",
    "ScenarioType",
    "Signal",
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
