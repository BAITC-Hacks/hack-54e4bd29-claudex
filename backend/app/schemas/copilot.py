"""HTTP-контракт необязательного пояснения сигнала."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ExplainSignalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: uuid.UUID


class CopilotFactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    metric_code: str
    label: str
    value: float
    unit: str
    direction: str
    period_start: datetime | None
    period_end: datetime | None
    source: str


class ExplainSignalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    signal_id: uuid.UUID
    signal_version: int
    title: str
    explanation: str
    fact_ids: list[str]
    facts: list[CopilotFactResponse]
    evaluation_period_start: date | None = None
    evaluation_period_end: date | None = None
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    data_current: bool
    data_watermark_at: datetime | None = None
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime
    request_id: str | None = None
    llm_generated: bool
    provider: str
    model: str
