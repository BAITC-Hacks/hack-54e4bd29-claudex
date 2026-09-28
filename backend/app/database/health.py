"""Проверка доступности зависимостей для readiness.

Проверки выполняются параллельно и каждая ограничена по времени:
readiness не должен зависеть от самой медленной зависимости
последовательно (DEPLOYMENT.md, раздел 7).

`/health` отвечает без обращения к зависимостям и означает живость
процесса. `/ready` означает готовность принимать трафик.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Literal

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database import clickhouse, object_storage, postgres, redis

logger = get_logger(__name__)

CheckResult = Literal["up", "down", "skipped"]


@dataclass(frozen=True, slots=True)
class DependencyReport:
    name: str
    status: CheckResult
    required: bool
    latency_ms: float | None = None
    reason: str | None = None


# Имя зависимости → функция проверки. Функция бросает исключение при отказе.
DEPENDENCY_CHECKS: dict[str, Callable[[float], None]] = {
    "postgres": postgres.check_connection,
    "clickhouse": clickhouse.check_connection,
    "redis": redis.check_connection,
    "object_storage": object_storage.check_connection,
}


def _short_reason(exc: BaseException) -> str:
    """Краткая причина без адресов, имён баз и трассировки.

    Подробности остаются в журнале: сообщение об отказе не должно
    раскрывать устройство внутренней сети.
    """
    return type(exc).__name__


def _run_check(name: str, timeout_s: float, required: bool) -> DependencyReport:
    check = DEPENDENCY_CHECKS.get(name)
    if check is None:
        return DependencyReport(
            name=name, status="skipped", required=required, reason="unknown_dependency"
        )

    started = time.perf_counter()
    try:
        check(timeout_s)
    except Exception as exc:
        logger.warning(
            "Зависимость недоступна",
            extra={"dependency": name, "required": required},
            exc_info=exc,
        )
        return DependencyReport(
            name=name,
            status="down",
            required=required,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            reason=_short_reason(exc),
        )

    return DependencyReport(
        name=name,
        status="up",
        required=required,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )


def collect_dependency_reports() -> list[DependencyReport]:
    """Проверить все зависимости и вернуть отчёт по каждой."""
    settings = get_settings()
    required = set(settings.required_dependencies)
    timeout_s = settings.readiness_timeout_s
    names = list(DEPENDENCY_CHECKS)

    reports: list[DependencyReport] = []
    with ThreadPoolExecutor(max_workers=len(names) or 1) as pool:
        futures = {
            pool.submit(_run_check, name, timeout_s, name in required): name
            for name in names
        }
        for future, name in futures.items():
            try:
                # Запас поверх собственного предела проверки: клиент, который
                # проигнорировал свой timeout, не должен подвесить readiness.
                reports.append(future.result(timeout=timeout_s + 2))
            except FutureTimeout:
                reports.append(
                    DependencyReport(
                        name=name,
                        status="down",
                        required=name in required,
                        reason="timeout",
                    )
                )

    reports.sort(key=lambda report: report.name)
    return reports


def is_ready(reports: list[DependencyReport]) -> bool:
    """Готовность определяется только обязательными зависимостями.

    Необязательные попадают в отчёт, но не влияют на код ответа:
    иначе готовность начинает мерцать из-за второстепенного сервиса.
    """
    return all(report.status == "up" for report in reports if report.required)
