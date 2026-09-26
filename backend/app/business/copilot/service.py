"""Безопасная сборка фактов и проверка LLM-пояснения сигнала."""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol

from app.business.copilot.rate_limit import LocalCopilotRateLimiter
from app.business.signals.service import SignalService
from app.core.exceptions import (
    CopilotDisabledError,
    CopilotInsufficientDataError,
    CopilotInvalidResponseError,
    CopilotProviderUnavailableError,
)
from app.models.enums import SignalType
from app.security.context import SecurityContext

_METRIC_LABELS = {
    "queue_size": "Размер очереди",
    "incoming_referrals": "Входящие направления",
    "refusal_rate": "Доля отказов в синтетическом примере",
    "composite_deviation": "Отклонение показателя в синтетическом примере",
}
_RULE_LABELS = {
    SignalType.QUEUE_GROWTH: "рост очереди",
    SignalType.HIGH_REFUSAL_RATE: "рост доли отказов",
    SignalType.DATA_STALE: "устаревшие данные",
    SignalType.ANOMALY_DETECTED: "аномалия показателя",
    SignalType.OVERLOAD_FORECAST: "прогнозный сигнал",
}
_NUMBER_WORDS = re.compile(
    r"\b(?:ноль|один|одна|два|две|три|четыре|пять|шесть|семь|восемь|"
    r"девять|десять|двадцать|тридцать|сорок|пятьдесят|шестьдесят|"
    r"семьдесят|восемьдесят|девяносто|сто|тысяч[а-я]*)\b",
    re.IGNORECASE,
)
_QUANTITATIVE = re.compile(r"\d|%|процент|п\.\s*п\.", re.IGNORECASE)
_TEMPORAL_CLAIMS = re.compile(
    r"январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|"
    r"октябр|ноябр|декабр|сегодня|сейчас|текущ[а-я]*",
    re.IGNORECASE,
)


class CopilotProvider(Protocol):
    """Один ответ по закрытому набору synthetic facts, без tools."""

    def explain(self, payload: dict[str, object]) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class CopilotFact:
    id: str
    metric_code: str
    label: str
    value: float
    unit: str
    direction: str
    period_start: datetime | None
    period_end: datetime | None
    source: str = "signal_explanation"


@dataclass(frozen=True, slots=True)
class CopilotResult:
    signal_id: uuid.UUID
    signal_version: int
    title: str
    explanation: str
    fact_ids: tuple[str, ...]
    facts: tuple[CopilotFact, ...]
    evaluation_period_start: date | None
    evaluation_period_end: date | None
    reference_period_start: date | None
    reference_period_end: date | None
    data_current: bool
    data_watermark_at: datetime | None
    limitations: tuple[str, ...]
    generated_at: datetime
    request_id: str | None
    llm_generated: bool
    provider: str
    model: str


def _is_synthetic_seed(signal: Any, *, demo_environment: bool) -> bool:
    """Four independent server-side provenance markers; client cannot set them."""
    return (
        demo_environment
        and signal.source == "SYNTHETIC_DEV_SEED"
        and signal.rule_version == "seed-0.1"
        and signal.rule_config.get("synthetic") is True
        and signal.evidence.get("synthetic") is True
        and signal.data_watermark.get("synthetic") is True
    )


def _facts_from_signal(signal: Any) -> tuple[CopilotFact, ...]:
    explanation = signal.explanation
    if explanation is None or explanation.generator_version != "seed-0.1":
        return ()
    start, end = explanation.input_period_start, explanation.input_period_end
    if start is not None and end is not None and start > end:
        return ()
    result: list[CopilotFact] = []
    for item in explanation.factors[:8]:
        if not isinstance(item, dict) or item.get("suppressed") is True:
            continue
        code = item.get("metric_code")
        value = item.get("change_pct")
        direction = item.get("direction")
        if (
            not isinstance(code, str)
            or code not in _METRIC_LABELS
            or isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or abs(value) > 1000
            or direction not in {"INCREASE", "DECREASE"}
        ):
            continue
        result.append(
            CopilotFact(
                id=f"F{len(result) + 1}",
                metric_code=code,
                label=_METRIC_LABELS[code],
                value=float(value),
                unit="percent_change",
                direction=direction,
                period_start=start,
                period_end=end,
            )
        )
    return tuple(result)


def _validate_model_output(
    raw: dict[str, object], facts: tuple[CopilotFact, ...]
) -> tuple[str, tuple[str, ...]]:
    if set(raw) != {"explanation", "fact_ids"}:
        raise CopilotInvalidResponseError()
    explanation = raw["explanation"]
    fact_ids = raw["fact_ids"]
    if (
        not isinstance(explanation, str)
        or not 40 <= len(explanation) <= 1500
        or _QUANTITATIVE.search(explanation)
        or _NUMBER_WORDS.search(explanation)
        or _TEMPORAL_CLAIMS.search(explanation)
        or "<" in explanation
        or ">" in explanation
        or "http://" in explanation.lower()
        or "https://" in explanation.lower()
        or not isinstance(fact_ids, list)
        or not fact_ids
        or len(fact_ids) > len(facts)
    ):
        raise CopilotInvalidResponseError()
    allowed = {fact.id for fact in facts}
    if any(not isinstance(item, str) or item not in allowed for item in fact_ids):
        raise CopilotInvalidResponseError()
    if len(fact_ids) != len(set(fact_ids)):
        raise CopilotInvalidResponseError()
    return explanation.strip(), tuple(fact_ids)


class CopilotService:
    """Проверяет scope и provenance до любого внешнего вызова."""

    def __init__(
        self,
        *,
        signals: SignalService,
        provider: CopilotProvider,
        enabled: bool,
        synthetic_demo_environment: bool,
        provider_name: str = "openai",
        model: str = "gpt-4.1-mini-2025-04-14",
        rate_limiter: LocalCopilotRateLimiter | None = None,
    ) -> None:
        self._signals = signals
        self._provider = provider
        self._enabled = enabled
        self._synthetic_demo_environment = synthetic_demo_environment
        self._provider_name = provider_name
        self._model = model
        self._rate_limiter = rate_limiter

    def explain_signal(
        self, context: SecurityContext, signal_id: uuid.UUID, *, request_id: str | None
    ) -> CopilotResult:
        if not self._enabled:
            raise CopilotDisabledError()
        detail = self._signals.get_signal(context, signal_id)
        signal = detail.signal
        if self._provider_name != "openai":
            raise CopilotProviderUnavailableError()
        if not _is_synthetic_seed(
            signal, demo_environment=self._synthetic_demo_environment
        ):
            raise CopilotInsufficientDataError()
        facts = _facts_from_signal(signal)
        if not facts:
            raise CopilotInsufficientDataError()
        if self._rate_limiter is not None:
            self._rate_limiter.check(context.user_id)

        # Never include title/summary, free-form factors, actions, audit,
        # user/signal/hospital IDs or raw evidence in provider input.
        payload: dict[str, object] = {
            "rule": signal.type.value,
            "facts": [
                {
                    "id": fact.id,
                    "metric_code": fact.metric_code,
                    "value": fact.value,
                    "unit": fact.unit,
                    "direction": fact.direction,
                    "period_start": fact.period_start.isoformat()
                    if fact.period_start
                    else None,
                    "period_end": fact.period_end.isoformat()
                    if fact.period_end
                    else None,
                }
                for fact in facts
            ],
            "limitations": ["synthetic_demo", "no_causality", "not_current_queue"],
        }
        explanation, fact_ids = _validate_model_output(
            self._provider.explain(payload), facts
        )
        return CopilotResult(
            signal_id=signal.id,
            signal_version=signal.version,
            title=f"Пояснение сигнала: {_RULE_LABELS[signal.type]}",
            explanation=explanation,
            fact_ids=fact_ids,
            facts=facts,
            evaluation_period_start=signal.evaluation_period_start,
            evaluation_period_end=signal.evaluation_period_end,
            reference_period_start=signal.reference_period_start,
            reference_period_end=signal.reference_period_end,
            data_current=signal.data_current,
            data_watermark_at=None,
            limitations=(
                "Синтетические данные не отражают реальную нагрузку.",
                "Факты не доказывают первопричину или наличие коек.",
                "Исторические данные не являются текущей очередью.",
                "Решение принимает уполномоченный сотрудник.",
            ),
            generated_at=datetime.now(tz=UTC),
            request_id=request_id,
            llm_generated=True,
            provider=self._provider_name,
            model=self._model,
        )
