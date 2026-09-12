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


class ScenarioType(StrEnum):
    INCOMING_FLOW_CHANGE = "INCOMING_FLOW_CHANGE"
    FLOW_REDISTRIBUTION = "FLOW_REDISTRIBUTION"


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
