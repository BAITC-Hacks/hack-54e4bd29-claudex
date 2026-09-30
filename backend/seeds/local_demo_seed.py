"""Seed only the explicitly opted-in, fresh local Kazakhstan demo directory.

Every organization and measurement is fictional. There are no patient records,
passwords, model outputs, or medical advice in this seed.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

from app.core.config import AppEnv, get_settings
from app.database.postgres import session_scope
from app.models.access import UserDataScope
from app.models.directory import Hospital, Region
from app.models.enums import (
    DataScopeType,
    ExplanationGenerator,
    FactorDirection,
    SignalSeverity,
    SignalSourceType,
    SignalStatus,
    SignalType,
)
from app.models.signal import Signal, SignalExplanation
from seeds.dev_seed import SYNTHETIC_MARK, USERS, _ensure_user

PROFILE_PATH = Path(__file__).with_name("local_demo_profile.json")
CUTOFF = date(2025, 3, 31)


def require_local_demo(settings_env: AppEnv, enabled: str | None) -> None:
    """Refuse accidental seed execution outside explicit local scope."""
    if settings_env is not AppEnv.LOCAL or enabled != "1":
        raise RuntimeError("Local synthetic demo requires explicit local opt-in")


def load_profile() -> tuple[dict[str, str], ...]:
    """Read canonical identities from the same reviewed JSON used by the host."""
    items = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(items, list) or len(items) != 12:
        raise ValueError("Local demo profile must contain exactly 12 regions")
    profile: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != {"code", "name"}
            or not isinstance(item["code"], str)
            or not isinstance(item["name"], str)
            or not item["code"].startswith("KZ-")
            or not item["name"].strip()
            or item["code"] in seen
        ):
            raise ValueError("Local demo profile contains an invalid or duplicate region")
        seen.add(item["code"])
        profile.append({"code": item["code"], "name": item["name"]})
    return tuple(profile)


def signal_evidence() -> dict[str, bool | str]:
    """State the historical cutoff, not an unsupported causal claim."""
    return {
        "synthetic": True,
        "confirmed_complete_through": CUTOFF.isoformat(),
    }


def seed() -> None:
    """Create a new local-only canonical directory and test-user scopes."""
    require_local_demo(get_settings().app_env, os.getenv("LOCAL_SYNTHETIC_DEMO"))
    profile = load_profile()
    now = datetime.now(tz=UTC)
    with session_scope() as session:
        if session.query(Region).count() or session.query(Hospital).count():
            raise RuntimeError("Local demo requires an empty canonical directory")

        regions: dict[str, Region] = {}
        hospitals: dict[str, Hospital] = {}
        for item in profile:
            code = item["code"]
            region = Region(
                id=uuid.uuid4(), code=code, name=f"{item['name']} {SYNTHETIC_MARK}"
            )
            hospital = Hospital(
                id=uuid.uuid4(),
                code=f"H-{code}",
                name=f"Условная клиника {item['name']} {SYNTHETIC_MARK}",
                region_id=region.id,
            )
            session.add_all((region, hospital))
            regions[code] = region
            hospitals[code] = hospital
        session.flush()

        first_code = profile[0]["code"]
        for subject, display_name, scope_type, _old_target in USERS:
            user = _ensure_user(session, subject, display_name)
            existing_scope = (
                session.query(UserDataScope).filter_by(user_id=user.id).first()
            )
            if existing_scope is not None:
                raise RuntimeError("Local demo user already has a data scope")
            session.add(
                UserDataScope(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    scope_type=scope_type,
                    region_id=regions[first_code].id
                    if scope_type is DataScopeType.REGION
                    else None,
                    hospital_id=hospitals[first_code].id
                    if scope_type is DataScopeType.HOSPITAL
                    else None,
                )
            )

        for code in ("KZ-ASTANA", "KZ-ALMATY", "KZ-KARAGANDA"):
            signal = Signal(
                id=uuid.uuid4(),
                scope_type=DataScopeType.HOSPITAL,
                hospital_id=hospitals[code].id,
                type=SignalType.DATA_STALE,
                severity=SignalSeverity.WARNING,
                status=SignalStatus.NEW,
                source_type=SignalSourceType.STATISTICAL,
                title=f"{SYNTHETIC_MARK} Исторический источник данных",
                summary=(
                    "Синтетический источник содержит наблюдения не позднее "
                    "31 марта 2025 года; это не текущая медицинская ситуация."
                ),
                evaluation_period_start=date(2025, 1, 1),
                evaluation_period_end=CUTOFF,
                detected_at=now,
                rule_code="SYNTHETIC_LOCAL_HISTORY_CUTOFF",
                rule_version="local-demo-v1",
                rule_config={"synthetic": True, "historical_cutoff": CUTOFF.isoformat()},
                evidence=signal_evidence(),
                source="SYNTHETIC_LOCAL_DEMO",
                data_watermark=signal_evidence(),
                data_current=False,
                dedup_key=sha256(f"local-demo:{code}:stale".encode()).hexdigest(),
                version=1,
            )
            session.add(signal)
            session.flush()
            session.add(
                SignalExplanation(
                    signal_id=signal.id,
                    summary=(
                        "Историческая дата подтверждения синтетической выгрузки: "
                        "31 марта 2025 года. Причина отсутствия более новых данных "
                        "не установлена."
                    ),
                    factors=[
                        {
                            "metric_code": "data_freshness_hours",
                            "direction": FactorDirection.INCREASE.value,
                            "change_pct": None,
                            "comparison_period": "после 2025-03-31",
                        }
                    ],
                    caveats=[
                        "Данные синтетические и не отражают реальную нагрузку",
                        "Сигнал не связан с прогнозом направлений",
                    ],
                    generator=ExplanationGenerator.STATISTICAL,
                    generator_version="local-demo-v1",
                    model_version=None,
                    input_period_start=datetime(2025, 1, 1, tzinfo=UTC),
                    input_period_end=datetime(2025, 3, 31, tzinfo=UTC),
                    generated_at=now,
                )
            )

    print("Local synthetic demo directory, scopes, and historical signals seeded")


if __name__ == "__main__":
    seed()
