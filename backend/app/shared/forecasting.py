"""Neutral data-transfer values shared by forecasting ports and adapters."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

REFERRAL_TARGET = "DAILY_REFERRAL_COUNT"


@dataclass(frozen=True, slots=True)
class DailyReferralCount:
    observed_on: date
    count: int


@dataclass(frozen=True, slots=True)
class ReferralDatasetWatermark:
    completed_at: datetime
    import_ids: tuple[uuid.UUID, ...]
    file_hashes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "completed_at": self.completed_at.isoformat(),
            "import_ids": [str(item) for item in self.import_ids],
            "file_hashes": list(self.file_hashes),
        }


@dataclass(frozen=True, slots=True)
class OrganizationForecastRequest:
    """Worker identity only; never accepts policy, artifact paths or approval."""

    hospital_id: uuid.UUID
    model_version: str
    mapping_version: str
    delivery_watermark: str
    origin: date
    horizon_days: int = 7


@dataclass(frozen=True, slots=True)
class OrganizationForecastInput:
    hospital_id: uuid.UUID
    mapping_version: str
    history: tuple[DailyReferralCount, ...]
    delivery_watermark: str
    as_of: datetime
    coverage_complete: bool = False
