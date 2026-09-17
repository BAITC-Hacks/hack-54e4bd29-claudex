"""HTTP endpoints for deterministic Scenario Analysis."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, ScenarioServiceDep
from app.api.v1.mappers import page_meta, scenario_preview_response, scenario_response
from app.business.simulation.contracts import ScenarioCommand, ScenarioScope
from app.models.enums import DataScopeType, ScenarioType
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.scenarios import (
    ScenarioCreateRequest,
    ScenarioListItem,
    ScenarioRequest,
    ScenarioResponse,
)
from app.shared.filters import ScenarioFilter
from app.shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, build_page_request

router = APIRouter(prefix="/scenarios", tags=["scenarios"], responses=ERROR_RESPONSES)
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]


def _command(payload: ScenarioRequest) -> ScenarioCommand:
    return ScenarioCommand(
        scenario_type=payload.scenario_type,
        scope=ScenarioScope(
            payload.scope_type,
            region_id=payload.region_id,
            hospital_id=payload.hospital_id,
        ),
        baseline_type=payload.baseline_type,
        assumption_value=payload.assumption_value,
        period_start=payload.period_start,
        period_end=payload.period_end,
        forecast_id=payload.forecast_id,
        historical_analysis=payload.historical_analysis,
        source_signal_id=payload.source_signal_id,
        source_incident_id=payload.source_incident_id,
    )


@router.post("/preview", response_model=ScenarioResponse)
def preview_scenario(
    payload: ScenarioRequest,
    context: CurrentUser,
    service: ScenarioServiceDep,
) -> ScenarioResponse:
    return scenario_preview_response(service.preview(context, _command(payload)))


@router.post("", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
def create_scenario(
    payload: ScenarioCreateRequest,
    context: CurrentUser,
    service: ScenarioServiceDep,
) -> ScenarioResponse:
    scenario = service.create(context, _command(payload), payload.client_request_id)
    return scenario_response(scenario)


@router.get("", response_model=Page[ScenarioListItem])
def list_scenarios(
    context: CurrentUser,
    service: ScenarioServiceDep,
    scenario_type: ScenarioType | None = None,
    scope_type: DataScopeType | None = None,
    source_signal_id: uuid.UUID | None = None,
    source_incident_id: uuid.UUID | None = None,
    page: PageNumber = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    sort_by: str | None = None,
    sort_desc: bool = True,
) -> Page[ScenarioListItem]:
    request = build_page_request(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_desc=sort_desc,
        allowed_sort_fields=frozenset({"created_at"}),
        default_sort_field="created_at",
    )
    result = service.list(
        context,
        ScenarioFilter(
            scenario_type=scenario_type,
            scope_type=scope_type,
            source_signal_id=source_signal_id,
            source_incident_id=source_incident_id,
        ),
        request,
    )
    return Page[ScenarioListItem](
        items=[
            ScenarioListItem(**scenario_response(item).model_dump())
            for item in result.items
        ],
        **page_meta(result),
    )


@router.get("/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(
    scenario_id: uuid.UUID,
    context: CurrentUser,
    service: ScenarioServiceDep,
) -> ScenarioResponse:
    return scenario_response(service.get(context, scenario_id))
