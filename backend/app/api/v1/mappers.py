"""Преобразование доменных объектов в контракты ответа.

Маршруты остаются тонкими, а состав ответа задаётся в одном месте.
Модели SQLAlchemy наружу не сериализуются: поля, добавленные в модель,
не должны появляться в ответе сами собой.
"""

from __future__ import annotations

from typing import Any

from app.business.incidents.service import IncidentDetail
from app.business.signals.service import SignalDetail
from app.models.audit import AuditEvent
from app.models.directory import Hospital, Region
from app.models.incident import Incident
from app.models.signal import Signal, SignalExplanation
from app.schemas.domain import (
    ActionResponse,
    AuditEventResponse,
    ExplanationFactor,
    HospitalListItem,
    HospitalResponse,
    IncidentListItem,
    IncidentResponse,
    RegionListItem,
    RegionResponse,
    SignalExplanationResponse,
    SignalListItem,
    SignalResponse,
)
from app.shared.pagination import Page as DomainPage


def page_meta(page: DomainPage[Any]) -> dict[str, Any]:
    """Поля страницы без содержимого.

    Элементы отображаются вызывающей стороной: только она знает,
    в какую схему их превращать.
    """
    return {
        "page": page.page,
        "page_size": page.page_size,
        "total": page.total,
        "has_next": page.has_next,
    }


# --- Справочники ------------------------------------------------------------


def region_list_item(region: Region) -> RegionListItem:
    return RegionListItem(
        id=region.id, code=region.code, name=region.name, is_active=region.is_active
    )


def region_response(region: Region) -> RegionResponse:
    return RegionResponse(
        id=region.id,
        code=region.code,
        name=region.name,
        is_active=region.is_active,
        created_at=region.created_at,
        updated_at=region.updated_at,
    )


def hospital_list_item(hospital: Hospital) -> HospitalListItem:
    return HospitalListItem(
        id=hospital.id,
        code=hospital.code,
        name=hospital.name,
        region_id=hospital.region_id,
        is_active=hospital.is_active,
    )


def hospital_response(hospital: Hospital) -> HospitalResponse:
    region = getattr(hospital, "region", None)
    return HospitalResponse(
        id=hospital.id,
        code=hospital.code,
        name=hospital.name,
        region_id=hospital.region_id,
        region_name=region.name if region is not None else None,
        is_active=hospital.is_active,
        created_at=hospital.created_at,
        updated_at=hospital.updated_at,
    )


# --- Сигналы ----------------------------------------------------------------


def _hospital_name(signal: Signal) -> str | None:
    hospital = getattr(signal, "hospital", None)
    return hospital.name if hospital is not None else None


def signal_list_item(signal: Signal) -> SignalListItem:
    return SignalListItem(
        id=signal.id,
        hospital_id=signal.hospital_id,
        hospital_name=_hospital_name(signal),
        type=signal.type,
        severity=signal.severity,
        status=signal.status,
        source_type=signal.source_type,
        title=signal.title,
        detected_at=signal.detected_at,
        assigned_user_id=signal.assigned_user_id,
        version=signal.version,
    )


def explanation_response(
    explanation: SignalExplanation | None,
) -> SignalExplanationResponse | None:
    if explanation is None:
        return None
    return SignalExplanationResponse(
        summary=explanation.summary,
        factors=[
            ExplanationFactor(
                metric_code=str(item.get("metric_code", "")),
                direction=str(item.get("direction", "")),
                change_pct=item.get("change_pct"),
                comparison_period=item.get("comparison_period"),
            )
            for item in explanation.factors
        ],
        caveats=list(explanation.caveats),
        generator=explanation.generator,
        generator_version=explanation.generator_version,
        model_version=explanation.model_version,
        input_period_start=explanation.input_period_start,
        input_period_end=explanation.input_period_end,
        generated_at=explanation.generated_at,
    )


def audit_event_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        id=event.id,
        actor_user_id=event.actor_user_id,
        action=event.action,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        request_id=event.request_id,
        metadata=event.event_metadata,
        created_at=event.created_at,
    )


def signal_response(detail: SignalDetail) -> SignalResponse:
    signal = detail.signal
    hospital = getattr(signal, "hospital", None)
    return SignalResponse(
        id=signal.id,
        hospital_id=signal.hospital_id,
        hospital_name=_hospital_name(signal),
        region_id=hospital.region_id if hospital is not None else None,
        type=signal.type,
        severity=signal.severity,
        status=signal.status,
        source_type=signal.source_type,
        title=signal.title,
        summary=signal.summary,
        detected_at=signal.detected_at,
        created_at=signal.created_at,
        updated_at=signal.updated_at,
        forecast_id=signal.forecast_id,
        incident_id=signal.incident_id,
        assigned_user_id=signal.assigned_user_id,
        closed_reason=signal.closed_reason,
        closed_at=signal.closed_at,
        version=signal.version,
        available_transitions=list(detail.available_transitions),
        explanation=explanation_response(signal.explanation),
        actions=[
            ActionResponse(
                id=action.id,
                action_type=action.action_type,
                description=action.description,
                created_by=action.created_by,
                created_at=action.created_at,
            )
            for action in detail.actions
        ],
        audit_history=[audit_event_response(event) for event in detail.audit_events],
    )


# --- Инциденты --------------------------------------------------------------


def incident_list_item(incident: Incident) -> IncidentListItem:
    return IncidentListItem(
        id=incident.id,
        hospital_id=incident.hospital_id,
        title=incident.title,
        status=incident.status,
        created_at=incident.created_at,
    )


def incident_response(detail: IncidentDetail) -> IncidentResponse:
    incident = detail.incident
    return IncidentResponse(
        id=incident.id,
        hospital_id=incident.hospital_id,
        title=incident.title,
        description=incident.description,
        status=incident.status,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        signals=[signal_list_item(signal) for signal in detail.signals],
    )
