"""Синтетические данные для разработки.

ВСЕ ДАННЫЕ ЗДЕСЬ ВЫМЫШЛЕНЫ. Реальных пациентов, ИИН, ФИО, телефонов,
адресов и любых персональных медицинских сведений в файле нет и быть
не может. Наименования организаций условны.

Назначение — проверить работу предметной области: области данных,
жизненный цикл сигнала, назначение ответственного. Показатели
не отражают реальную нагрузку и не пригодны ни для каких выводов.

Запуск:
    docker compose run --rm backend python -m seeds.dev_seed
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import AppEnv, get_settings
from app.database.postgres import session_scope
from app.models.access import User, UserDataScope
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

# Пометка проставляется каждому созданному объекту: происхождение данных
# должно быть очевидно любому, кто откроет базу.
SYNTHETIC_MARK = "[синтетические данные]"


def _now() -> datetime:
    return datetime.now(tz=UTC)


REGIONS = [
    ("R-A", "Регион А"),
    ("R-B", "Регион Б"),
]

HOSPITALS = [
    ("H-A1", "Медицинская организация A1", "R-A"),
    ("H-A2", "Медицинская организация A2", "R-A"),
    ("H-B1", "Медицинская организация B1", "R-B"),
]

# Субъекты соответствуют служебному клиенту области разработки Keycloak.
# Паролей здесь нет: MedSignal их не хранит (ADR-0009).
USERS = [
    ("dev-admin", "Администратор (dev)", DataScopeType.GLOBAL, None),
    ("dev-region-a", "Аналитик региона А (dev)", DataScopeType.REGION, "R-A"),
    ("dev-hospital-a1", "Руководитель A1 (dev)", DataScopeType.HOSPITAL, "H-A1"),
]

SIGNALS = [
    ("H-A1", SignalType.QUEUE_GROWTH, SignalSeverity.HIGH, SignalStatus.NEW, 2),
    ("H-A1", SignalType.DATA_STALE, SignalSeverity.WARNING, SignalStatus.NEW, 5),
    ("H-A2", SignalType.HIGH_REFUSAL_RATE, SignalSeverity.CRITICAL, SignalStatus.NEW, 1),
    (
        "H-A2",
        SignalType.ANOMALY_DETECTED,
        SignalSeverity.INFO,
        SignalStatus.IN_PROGRESS,
        7,
    ),
    ("H-B1", SignalType.QUEUE_GROWTH, SignalSeverity.WARNING, SignalStatus.NEW, 3),
]


def _guard_environment() -> None:
    """Не давать наполнить синтетикой ничего, кроме локальной среды."""
    settings = get_settings()
    if settings.app_env is not AppEnv.LOCAL:
        print(
            f"[medsignal] Отказ: наполнение синтетическими данными допустимо "
            f"только при APP_ENV=local, текущее значение {settings.app_env.value}",
            file=sys.stderr,
        )
        raise SystemExit(78)


def _explanation_for(signal: Signal, signal_type: SignalType) -> SignalExplanation:
    """Объяснение со сведениями о происхождении.

    Собрано детерминированным кодом, а не языковой моделью: происхождение
    каждого утверждения должно быть восстановимо.
    """
    factors = {
        SignalType.QUEUE_GROWTH: [
            {
                "metric_code": "queue_size",
                "direction": FactorDirection.INCREASE.value,
                "change_pct": 21.0,
                "comparison_period": "14 дней к предыдущим 14",
            },
            {
                "metric_code": "incoming_referrals",
                "direction": FactorDirection.INCREASE.value,
                "change_pct": 14.0,
                "comparison_period": "14 дней к предыдущим 14",
            },
        ],
        SignalType.HIGH_REFUSAL_RATE: [
            {
                "metric_code": "refusal_rate",
                "direction": FactorDirection.INCREASE.value,
                "change_pct": 38.0,
                "comparison_period": "7 дней к собственной норме",
            }
        ],
        SignalType.DATA_STALE: [
            {
                "metric_code": "data_freshness_hours",
                "direction": FactorDirection.INCREASE.value,
                "change_pct": None,
                "comparison_period": "с момента последней выгрузки",
            }
        ],
    }.get(
        signal_type,
        [
            {
                "metric_code": "composite_deviation",
                "direction": FactorDirection.INCREASE.value,
                "change_pct": 12.0,
                "comparison_period": "7 дней к собственной норме",
            }
        ],
    )

    return SignalExplanation(
        signal_id=signal.id,
        summary=f"{SYNTHETIC_MARK} Отклонение относительно собственной нормы организации",
        factors=factors,
        caveats=[
            "Данные синтетические и не отражают реальную нагрузку",
            "Объяснение показывает, что повлияло на расчёт, а не установленную причину",
        ],
        generator=ExplanationGenerator.STATISTICAL,
        generator_version="seed-0.1",
        model_version=None,
        input_period_start=_now() - timedelta(days=28),
        input_period_end=_now(),
        generated_at=_now(),
    )


def seed() -> None:
    _guard_environment()

    with session_scope() as session:
        if session.query(Region).count() > 0:
            print("[medsignal] Справочники уже наполнены, повторный запуск пропущен")
            return

        regions: dict[str, Region] = {}
        for code, name in REGIONS:
            region = Region(id=uuid.uuid4(), code=code, name=f"{name} {SYNTHETIC_MARK}")
            session.add(region)
            regions[code] = region

        hospitals: dict[str, Hospital] = {}
        for code, name, region_code in HOSPITALS:
            hospital = Hospital(
                id=uuid.uuid4(),
                code=code,
                name=f"{name} {SYNTHETIC_MARK}",
                region_id=regions[region_code].id,
            )
            session.add(hospital)
            hospitals[code] = hospital

        session.flush()

        for subject, display_name, scope_type, target in USERS:
            user = User(
                id=uuid.uuid4(), external_subject=subject, display_name=display_name
            )
            session.add(user)
            session.flush()
            session.add(
                UserDataScope(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    scope_type=scope_type,
                    region_id=regions[target].id
                    if scope_type is DataScopeType.REGION
                    else None,
                    hospital_id=hospitals[target].id
                    if scope_type is DataScopeType.HOSPITAL
                    else None,
                )
            )

        for hospital_code, signal_type, severity, status, days_ago in SIGNALS:
            signal = Signal(
                id=uuid.uuid4(),
                hospital_id=hospitals[hospital_code].id,
                type=signal_type,
                severity=severity,
                status=status,
                source_type=SignalSourceType.STATISTICAL,
                title=f"{SYNTHETIC_MARK} {signal_type.value}",
                summary=(
                    "Синтетический сигнал для проверки предметной области. "
                    "Реальных наблюдений за ним нет."
                ),
                detected_at=_now() - timedelta(days=days_ago),
                version=1,
            )
            session.add(signal)
            session.flush()
            session.add(_explanation_for(signal, signal_type))

    print(
        f"[medsignal] Создано: регионов {len(REGIONS)}, организаций "
        f"{len(HOSPITALS)}, пользователей {len(USERS)}, сигналов {len(SIGNALS)}. "
        f"Все данные синтетические."
    )


if __name__ == "__main__":
    seed()
