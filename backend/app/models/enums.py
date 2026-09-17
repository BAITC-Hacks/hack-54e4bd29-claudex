"""Перечисления предметной области.

Модуль намеренно не зависит ни от SQLAlchemy, ни от Pydantic: значения
нужны и моделям, и схемам, и бизнес-слою. Общая точка определения
исключает расхождение строковых констант между слоями.
"""

from __future__ import annotations

from enum import StrEnum


class SignalType(StrEnum):
    """Тип сигнала (BUSINESS_LOGIC.md, раздел 4.1)."""

    QUEUE_GROWTH = "QUEUE_GROWTH"
    HIGH_REFUSAL_RATE = "HIGH_REFUSAL_RATE"
    OVERLOAD_FORECAST = "OVERLOAD_FORECAST"
    DATA_STALE = "DATA_STALE"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    DATA_QUALITY_DEGRADED = "DATA_QUALITY_DEGRADED"
    REFERRAL_SPIKE = "REFERRAL_SPIKE"
    REFUSAL_SPIKE = "REFUSAL_SPIKE"
    FORECAST_INFLOW_GROWTH = "FORECAST_INFLOW_GROWTH"


class SignalSourceType(StrEnum):
    """Источник, породивший сигнал (ADR-0008).

    Три источника независимы: отказ одного не останавливает остальные.
    """

    RULE_BASED = "RULE_BASED"
    STATISTICAL = "STATISTICAL"
    ML_BASED = "ML_BASED"


class SignalSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SignalStatus(StrEnum):
    """Статус сигнала. Переходы описаны в business/signals/state_machine.py."""

    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"

    @property
    def is_terminal(self) -> bool:
        return self is SignalStatus.CLOSED


class SignalClosureDisposition(StrEnum):
    """Human interpretation of a closed Signal."""

    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ActionType(StrEnum):
    """Тип действия человека.

    Это действия уполномоченного сотрудника, а не рекомендации системы.
    Записи, порождённые автоматикой, действиями не считаются
    (BUSINESS_LOGIC.md, раздел 8).
    """

    STATUS_CHANGE = "STATUS_CHANGE"
    ASSIGNMENT = "ASSIGNMENT"
    COMMENT = "COMMENT"
    DECISION_RECORDED = "DECISION_RECORDED"


class ExplanationGenerator(StrEnum):
    """Кто построил объяснение.

    Языковые модели в перечне отсутствуют намеренно: объяснение строится
    детерминированным кодом по данным, и его происхождение должно быть
    восстановимо (BUSINESS_LOGIC.md, раздел 5).
    """

    RULE_ENGINE = "RULE_ENGINE"
    STATISTICAL = "STATISTICAL"
    MODEL_ATTRIBUTION = "MODEL_ATTRIBUTION"


class FactorDirection(StrEnum):
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    STABLE = "STABLE"


class ForecastStatus(StrEnum):
    """Состояние прогноза.

    `INVALID` означает, что прогноз построен, но не прошёл проверку
    качества и не используется в оценке риска и в сигналах
    (ML_ARCHITECTURE.md, раздел 6.2).
    """

    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"
    FAILED = "FAILED"


class ModelVersionStatus(StrEnum):
    """Lifecycle of a registered forecasting candidate."""

    SELECTED = "SELECTED"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


class ScenarioType(StrEnum):
    REFERRAL_INFLOW_CHANGE = "REFERRAL_INFLOW_CHANGE"


class ScenarioBaselineType(StrEnum):
    OBSERVED = "OBSERVED"
    FORECAST = "FORECAST"


class BaselineFreshnessStatus(StrEnum):
    """Временная актуальность baseline, не валидность Forecast."""

    CURRENT = "CURRENT"
    STALE = "STALE"


class ScenarioStatus(StrEnum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DataImportStatus(StrEnum):
    """Жизненный цикл долгой операции (ADR-0010)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in (DataImportStatus.COMPLETED, DataImportStatus.FAILED)


class DataScopeType(StrEnum):
    """Вид области данных пользователя."""

    GLOBAL = "GLOBAL"
    REGION = "REGION"
    HOSPITAL = "HOSPITAL"


class AuditAction(StrEnum):
    """Действия, попадающие в неизменяемый журнал.

    Перечень закрыт: произвольная строка в журнале аудита делает его
    непригодным для машинного разбора при расследовании.
    """

    SIGNAL_STATUS_CHANGED = "SIGNAL_STATUS_CHANGED"
    SIGNAL_ASSIGNED = "SIGNAL_ASSIGNED"
    SIGNAL_UNASSIGNED = "SIGNAL_UNASSIGNED"
    SIGNAL_CREATED = "SIGNAL_CREATED"
    SIGNAL_ACKNOWLEDGED = "SIGNAL_ACKNOWLEDGED"
    SIGNAL_RESOLVED = "SIGNAL_RESOLVED"
    SIGNAL_DISMISSED = "SIGNAL_DISMISSED"
    INCIDENT_CREATED_FROM_SIGNAL = "INCIDENT_CREATED_FROM_SIGNAL"
    INCIDENT_ASSIGNED = "INCIDENT_ASSIGNED"
    INCIDENT_STATUS_CHANGED = "INCIDENT_STATUS_CHANGED"
    INCIDENT_CHANGED = "INCIDENT_CHANGED"
    SCENARIO_CREATED = "SCENARIO_CREATED"
    ACTION_RECORDED = "ACTION_RECORDED"
    DATA_IMPORT_REGISTERED = "DATA_IMPORT_REGISTERED"
    AUDIT_VIEWED = "AUDIT_VIEWED"


class AuditEntityType(StrEnum):
    SIGNAL = "SIGNAL"
    INCIDENT = "INCIDENT"
    SCENARIO = "SCENARIO"
    ACTION = "ACTION"
    DATA_IMPORT = "DATA_IMPORT"
    AUDIT_LOG = "AUDIT_LOG"


class DatasetType(StrEnum):
    """Наборы данных, которые система принимает.

    Перечень закрыт намеренно. Он же служит разрешающим списком: набора,
    которого здесь нет, загрузить нельзя. Выгрузки о вакцинации и
    онкологии в задаче о нагрузке стационаров не участвуют, и попадание
    ста миллионов записей в хранилище «за компанию» исключено правилом,
    а не внимательностью оператора.
    """

    REFERRALS = "REFERRALS"
    WAITING = "WAITING"
    REFUSALS = "REFUSALS"
    TREATED = "TREATED"


class SourceSystem(StrEnum):
    """Информационная система, из которой пришла выгрузка."""

    IS_BG = "ИС БГ"
    ERSB = "ЭРСБ"


class MappingStatus(StrEnum):
    """Состояние сопоставления значения источника со справочником."""

    UNMAPPED = "UNMAPPED"
    MAPPED = "MAPPED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class MappingMethod(StrEnum):
    """Чем подтверждено сопоставление.

    Автоматического подбора по похожести здесь нет и не будет. Склейка
    двух наименований организаций меняет смысл данных, и основанием
    для неё может быть только официальный справочник или решение
    человека.
    """

    OFFICIAL_REFERENCE = "OFFICIAL_REFERENCE"
    MANUAL_APPROVED = "MANUAL_APPROVED"


class QualitySeverity(StrEnum):
    """Уровень замечания о качестве загруженных данных."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
