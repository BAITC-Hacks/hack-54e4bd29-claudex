"""Approved aggregate evaluation. No raw file access, training or backend imports."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import TypedDict

from ml.monitoring_contracts import (
    AggregateManifest,
    AggregateSeries,
    DailyObservation,
    FrozenProtocol,
    SplitSpec,
    TrainingSample,
    canonical_sha256,
    label_within_training,
)

_Predictor = Callable[[list[tuple[float, ...]]], Iterable[float]]


class _UncertaintyResult(TypedDict):
    method: str
    seed: int
    resamples: int
    confidence: float
    organization_clusters: int
    time_blocks: int
    intervals: dict[str, list[float] | None] | None
    reason: str | None
    valid_resamples: dict[str, int]


def load_approved_aggregates(
    rows: list[dict], manifest: AggregateManifest
) -> tuple[AggregateSeries, ...]:
    """Consume D's trusted approved population/delivery projection, never raw CSV."""
    if canonical_sha256(rows) != manifest.aggregate_sha256:
        raise ValueError("Aggregate hash mismatch")
    counts = {}
    for row in rows:
        if type(row) is not dict or set(row) != {"organization_id", "day", "value"}:
            raise ValueError("Only approved daily aggregate fields accepted")
        if row["organization_id"] not in manifest.organizations:
            raise ValueError("Organization outside approved reporting population")
        try:
            day = date.fromisoformat(row["day"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid aggregate day") from exc
        if not manifest.period_start <= day <= manifest.period_end:
            raise ValueError("Aggregate day outside manifest")
        if type(row["value"]) is not int or row["value"] < 0:
            raise ValueError("Counts must be nonnegative integers")
        key = row["organization_id"], day
        if key in counts:
            raise ValueError("Duplicate organization-day aggregate")
        counts[key] = row["value"]
    result = []
    for org in sorted(manifest.organizations):
        observations = []
        for offset in range((manifest.period_end - manifest.period_start).days + 1):
            day = manifest.period_start + timedelta(days=offset)
            complete = (
                manifest.confirmed_complete_through is not None
                and day <= manifest.confirmed_complete_through
            )
            observations.append(
                DailyObservation(
                    day, counts.get((org, day), 0) if complete else None, complete
                )
            )
        result.append(
            AggregateSeries(
                org, tuple(observations), manifest.mapping_available_on, manifest.sha256
            )
        )
    return tuple(result)


def _history(series: AggregateSeries, start: date, end: date) -> tuple[int, ...] | None:
    observations = tuple(o for o in series.observations if start <= o.day <= end)
    if len(observations) != (end - start).days + 1 or any(
        not o.delivery_complete for o in observations
    ):
        return None
    values: list[int] = []
    for observation in observations:
        # DailyObservation enforces complete -> non-None at construction.
        value = observation.value
        assert value is not None
        values.append(value)
    return tuple(values)


def features_at(
    series: AggregateSeries, origin: date, horizon: int
) -> tuple[float, ...] | None:
    if type(horizon) is not int or not 1 <= horizon <= 7:
        raise ValueError("Horizon must be 1..7")
    if series.mapping_available_on > origin:
        return None
    hist = _history(series, origin - timedelta(days=27), origin)
    if hist is None:
        return None
    return (
        hist[-1],
        hist[-2],
        hist[-3],
        hist[-7],
        hist[-14],
        mean(hist[-7:]),
        mean(hist[-14:]),
        mean(hist),
        pstdev(hist[-7:]),
        hist[horizon - 8],
        (origin + timedelta(days=horizon)).weekday(),
        horizon,
    )


def eligible_organizations(
    series: Sequence[AggregateSeries],
    split: SplitSpec,
    minimum_total: int = 1,
    minimum_days: int = 28,
) -> tuple[str, ...]:
    if (
        type(minimum_total) is not int
        or minimum_total < 0
        or type(minimum_days) is not int
        or minimum_days < 28
    ):
        raise ValueError("Invalid eligibility criteria")
    result = []
    for item in series:
        training = [o for o in item.observations if o.day <= split.train_end]
        if (
            item.mapping_available_on <= split.train_end
            and len(training) >= minimum_days
            and all(o.delivery_complete for o in training)
            and sum(o.value for o in training if o.value is not None) >= minimum_total
        ):
            result.append(item.organization_id)
    return tuple(sorted(result))


def training_samples(
    series: Sequence[AggregateSeries], split: SplitSpec
) -> tuple[TrainingSample, ...]:
    result = []
    for item in series:
        for observation in item.observations:
            origin = observation.day
            if not label_within_training(origin, split):
                continue
            x = tuple(features_at(item, origin, h) for h in range(1, 8))
            y = _history(item, origin + timedelta(days=1), origin + timedelta(days=7))
            if all(row is not None for row in x) and y is not None:
                known_x = tuple(row for row in x if row is not None)
                result.append(TrainingSample(item.organization_id, origin, known_x, y))
    return tuple(result)


def forecast_at(
    series: Sequence[AggregateSeries], origin: date, predictor: _Predictor
) -> dict:
    if len({s.organization_id for s in series}) != len(series):
        raise ValueError("Duplicate organizations")
    x = [features_at(item, origin, h) for item in series for h in range(1, 8)]
    if not x or any(row is None for row in x):
        return {"status": "INSUFFICIENT_DATA", "forecasts": {}}
    # The preceding guard excludes every UNKNOWN feature row.
    known_x = [row for row in x if row is not None]
    values = list(predictor(known_x))
    if len(values) != len(x) or any(
        isinstance(v, bool)
        or not isinstance(v, int | float)
        or not math.isfinite(v)
        or v < 0
        for v in values
    ):
        raise ValueError(
            "Predictor must return finite nonnegative counts for every horizon"
        )
    return {
        "status": "PASS",
        "forecasts": {
            item.organization_id: [float(v) for v in values[i * 7 : (i + 1) * 7]]
            for i, item in enumerate(series)
        },
    }


def forecast_metrics(actual: Sequence[float], predicted: Sequence[float]) -> dict:
    if len(actual) != len(predicted) or any(
        isinstance(v, bool)
        or not isinstance(v, int | float)
        or not math.isfinite(v)
        or v < 0
        for v in (*actual, *predicted)
    ):
        raise ValueError("Aligned finite nonnegative observations required")
    if not actual:
        return {"mae": None, "wape": None, "points": 0}
    error = sum(abs(a - p) for a, p in zip(actual, predicted, strict=False))
    return {
        "mae": error / len(actual),
        "wape": error / sum(actual) * 100 if sum(actual) else None,
        "points": len(actual),
    }


def walk_forward_score(
    series: Sequence[AggregateSeries],
    split: SplitSpec,
    predictor: _Predictor,
    partition: str = "validation",
    minimum_total: int = 1,
    minimum_days: int = 28,
) -> dict:
    if partition not in ("validation", "test"):
        raise ValueError("Expected validation or test partition")
    lower, upper = (
        (split.train_end, split.validation_end)
        if partition == "validation"
        else (split.validation_end, split.test_end)
    )
    eligible = set(
        eligible_organizations(
            series, split, minimum_total=minimum_total, minimum_days=minimum_days
        )
    )
    selected = tuple(s for s in series if s.organization_id in eligible)
    total: dict[str, list[float]] = {
        "actual": [],
        "ml": [],
        "weekly_naive": [],
        "mean7": [],
    }
    windows: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    episodes: list[AlertEpisode] = []
    origin = lower
    while origin + timedelta(days=7) <= upper:
        truth = [
            _history(item, origin + timedelta(days=1), origin + timedelta(days=7))
            for item in selected
        ]
        predictions = (
            forecast_at(selected, origin, predictor)
            if truth and all(values is not None for values in truth)
            else {"status": "INSUFFICIENT_DATA"}
        )
        if predictions["status"] != "PASS":
            excluded.append(
                {"origin": origin.isoformat(), "reason": "UNKNOWN_COVERAGE_OR_MAPPING"}
            )
            episodes.extend(
                AlertEpisode(item.organization_id, origin + timedelta(days=1), None, None)
                for item in selected
            )
        else:
            fold: dict[str, list[float]] = {
                "actual": [],
                "ml": [],
                "weekly_naive": [],
                "mean7": [],
            }
            for item, actual in zip(selected, truth, strict=False):
                history = _history(item, origin - timedelta(days=6), origin)
                reference = _history(item, origin - timedelta(days=27), origin)
                # PASS requires complete targets and 28-day feature history above.
                assert actual is not None
                assert history is not None
                assert reference is not None
                reference_total = sum(reference) / 4
                forecast_total = sum(predictions["forecasts"][item.organization_id])
                predicted_growth = (
                    reference_total >= 20
                    and forecast_total - reference_total >= 10
                    and forecast_total >= reference_total * 1.2
                )
                episodes.append(
                    AlertEpisode(
                        item.organization_id,
                        origin + timedelta(days=1),
                        growth_label(reference, actual),
                        predicted_growth,
                        origin if predicted_growth else None,
                    )
                )
                fold["actual"].extend(actual)
                fold["ml"].extend(predictions["forecasts"][item.organization_id])
                fold["weekly_naive"].extend(history)
                fold["mean7"].extend([mean(history)] * 7)
            windows.append(
                {
                    "origin": origin.isoformat(),
                    "start": (origin + timedelta(days=1)).isoformat(),
                    "end": (origin + timedelta(days=7)).isoformat(),
                    **{
                        key: forecast_metrics(fold["actual"], fold[key])
                        for key in ("ml", "weekly_naive", "mean7")
                    },
                }
            )
            for key in total:
                total[key].extend(fold[key])
        origin += timedelta(days=7)
    return {
        "status": "PASS" if windows and not excluded else "INSUFFICIENT_DATA",
        "windows": windows,
        "excluded_windows": excluded,
        "episodes": tuple(episodes),
        **{
            key: forecast_metrics(total["actual"], total[key])
            for key in ("ml", "weekly_naive", "mean7")
        },
    }


@dataclass(frozen=True)
class AlertCounts:
    tp: int
    fp: int
    fn: int
    tn: int

    def __post_init__(self) -> None:
        if any(type(v) is not int or v < 0 for v in (self.tp, self.fp, self.fn, self.tn)):
            raise ValueError("Episode counts must be nonnegative integers")


def precision(counts: AlertCounts) -> float | None:
    return counts.tp / (counts.tp + counts.fp) if counts.tp + counts.fp else None


def recall(counts: AlertCounts) -> float | None:
    return counts.tp / (counts.tp + counts.fn) if counts.tp + counts.fn else None


@dataclass(frozen=True)
class AlertEpisode:
    organization_id: str
    window_start: date
    actual_positive: bool | None
    predicted_positive: bool | None
    issued_on: date | None = None


def _validate_episodes(episodes: Sequence[AlertEpisode]) -> None:
    keys = set()
    anchor = min((e.window_start for e in episodes), default=None)
    for episode in episodes:
        if (
            not isinstance(episode.organization_id, str)
            or not episode.organization_id.strip()
            or type(episode.window_start) is not date
        ):
            raise ValueError("Approved organization and episode day required")
        if any(
            v is not None and type(v) is not bool
            for v in (episode.actual_positive, episode.predicted_positive)
        ):
            raise ValueError("Episode labels must be boolean or UNKNOWN")
        key = episode.organization_id, episode.window_start
        # Iteration proves the sequence was nonempty when its minimum was taken.
        assert anchor is not None
        if key in keys or (episode.window_start - anchor).days % 7:
            raise ValueError("Duplicate, overlapping or unaligned weekly episodes")
        keys.add(key)
        if episode.issued_on is not None and (
            type(episode.issued_on) is not date
            or episode.issued_on > episode.window_start
            or episode.predicted_positive is not True
        ):
            raise ValueError("Alert must be issued by window start")


def _count_episodes(episodes: Sequence[AlertEpisode]) -> AlertCounts:
    return AlertCounts(
        sum(e.actual_positive is True and e.predicted_positive is True for e in episodes),
        sum(
            e.actual_positive is False and e.predicted_positive is True for e in episodes
        ),
        sum(
            e.actual_positive is True and e.predicted_positive is False for e in episodes
        ),
        sum(
            e.actual_positive is False and e.predicted_positive is False for e in episodes
        ),
    )


def episode_metrics(episodes: Sequence[AlertEpisode]) -> dict:
    _validate_episodes(episodes)
    known = [
        e
        for e in episodes
        if e.actual_positive is not None and e.predicted_positive is not None
    ]
    counts = _count_episodes(known)
    lead = [
        (e.window_start - e.issued_on).days
        for e in known
        if e.actual_positive and e.predicted_positive and e.issued_on is not None
    ]
    return {
        "counts": asdict(counts),
        "precision": precision(counts),
        "recall": recall(counts),
        "alerts_per_org_week": (counts.tp + counts.fp) / len(known) if known else None,
        "false_alerts_per_org_week": counts.fp / len(known) if known else None,
        "sample_support": {
            "organizations": len({e.organization_id for e in known}),
            "evaluation_windows": len({e.window_start for e in known}),
            "org_weeks": len(known),
            "positive_episodes": counts.tp + counts.fn,
        },
        "lead_time_days": mean(lead) if lead else None,
        "lead_time_supported_episodes": len(lead),
        "excluded_episodes": len(episodes) - len(known),
    }


def daily_alert_clusters(records: Sequence[tuple[str, date]]) -> dict:
    if len(set(records)) != len(records):
        raise ValueError("Duplicate daily alert")
    previous: dict[str, date] = {}
    counts: dict[str, int] = {}
    for org, day in sorted(records):
        if not org or type(day) is not date:
            raise ValueError("Organization and date required")
        if org not in previous or day != previous[org] + timedelta(days=1):
            counts[org] = counts.get(org, 0) + 1
        previous[org] = day
    return {
        "alert_days": len(records),
        "clusters": sum(counts.values()),
        "by_organization": counts,
    }


def growth_label(
    reference_days: Sequence[int | None], outcome_days: Sequence[int | None]
) -> bool | None:
    if len(reference_days) != 28 or len(outcome_days) != 7:
        raise ValueError("Growth reference requires 28 prior days and 7 outcome days")
    values = [*reference_days, *outcome_days]
    if any(v is not None and (type(v) is not int or v < 0) for v in values):
        raise ValueError("Invalid aggregate count")
    if any(v is None for v in values):
        return None
    # All UNKNOWN values returned above; these filters only narrow the types.
    reference = sum(value for value in reference_days if value is not None) / 4
    actual = sum(value for value in outcome_days if value is not None)
    return reference >= 20 and actual - reference >= 10 and actual >= reference * 1.2


def cluster_uncertainty(
    episodes: Sequence[AlertEpisode],
    *,
    seed: int,
    resamples: int = 2000,
    min_organizations: int = 2,
    min_time_blocks: int = 4,
) -> _UncertaintyResult:
    """Crossed cluster bootstrap; never resample correlated daily rows as trials."""
    _validate_episodes(episodes)
    if (
        type(seed) is not int
        or type(resamples) is not int
        or resamples < 100
        or type(min_organizations) is not int
        or min_organizations < 2
        or type(min_time_blocks) is not int
        or min_time_blocks < 4
    ):
        raise ValueError("Invalid bootstrap settings")
    known = [
        e
        for e in episodes
        if e.actual_positive is not None and e.predicted_positive is not None
    ]
    orgs = sorted({e.organization_id for e in known})
    blocks = sorted({e.window_start for e in known})
    result: _UncertaintyResult = {
        "method": "crossed-organization-week-bootstrap",
        "seed": seed,
        "resamples": resamples,
        "confidence": 0.95,
        "organization_clusters": len(orgs),
        "time_blocks": len(blocks),
        "intervals": None,
        "reason": None,
        "valid_resamples": {},
    }
    if len(orgs) < min_organizations or len(blocks) < min_time_blocks:
        result["reason"] = "TOO_FEW_INDEPENDENT_CLUSTERS"
        return result
    rng = random.Random(seed)  # noqa: S311 - reproducible statistics, not cryptography
    lookup = {(e.organization_id, e.window_start): e for e in known}
    draws: dict[str, list[float]] = {
        "precision": [],
        "recall": [],
        "false_alerts_per_org_week": [],
    }
    for _ in range(resamples):
        sampled_orgs = rng.choices(orgs, k=len(orgs))
        sampled_blocks = rng.choices(blocks, k=len(blocks))
        sample = [
            lookup[(org, block)]
            for org in sampled_orgs
            for block in sampled_blocks
            if (org, block) in lookup
        ]
        counts = _count_episodes(sample)
        for key, value in (
            ("precision", precision(counts)),
            ("recall", recall(counts)),
            ("false_alerts_per_org_week", counts.fp / len(sample) if sample else None),
        ):
            if value is not None:
                draws[key].append(value)
    import numpy as np

    result["valid_resamples"] = {key: len(values) for key, values in draws.items()}
    intervals: dict[str, list[float] | None] = {
        key: [float(v) for v in np.quantile(values, [0.025, 0.975])]
        if len(values) >= 0.8 * resamples
        else None
        for key, values in draws.items()
    }
    result["intervals"] = intervals
    if any(value is None for value in intervals.values()):
        result["reason"] = "TOO_MANY_UNDEFINED_RESAMPLES"
    return result


def evaluate_protocol(
    rows: list[dict[str, object]],
    manifest: AggregateManifest,
    protocol: FrozenProtocol,
    predictor: _Predictor,
    *,
    partition: str = "validation",
) -> dict:
    """Apply the frozen protocol to approved aggregates; this does not grant admission.

    The caller controls sealed-test access. Repeated inference is reproducibility
    only, never a second independent evaluation.
    """
    from ml.monitoring_contracts import freeze_protocol

    payload = freeze_protocol(protocol.snapshot()).snapshot()
    if (
        payload["aggregate_manifest_sha256"] != manifest.sha256
        or payload["dataset_sha256"] != manifest.aggregate_sha256
        or payload["mapping_version"] != manifest.mapping_version
    ):
        raise ValueError("Protocol provenance does not match approved aggregates")
    split = SplitSpec(
        date.fromisoformat(payload["split"]["train_end"]),
        date.fromisoformat(payload["split"]["validation_end"]),
        date.fromisoformat(payload["split"]["test_end"]),
    )
    all_series = load_approved_aggregates(rows, manifest)
    eligibility = payload["eligibility"]
    eligible = set(
        eligible_organizations(
            all_series,
            split,
            minimum_total=eligibility["minimum_training_total"],
            minimum_days=eligibility["minimum_training_days"],
        )
    )
    selected = tuple(s for s in all_series if s.organization_id in eligible)
    scores = walk_forward_score(
        selected,
        split,
        predictor,
        partition=partition,
        minimum_total=eligibility["minimum_training_total"],
        minimum_days=eligibility["minimum_training_days"],
    )
    episodes = scores.pop("episodes")
    return {
        **scores,
        "protocol_sha256": protocol.sha256,
        "dataset_sha256": manifest.aggregate_sha256,
        "baseline": payload["baseline_selection"]["selected"],
        "eligible_organizations": tuple(sorted(eligible)),
        "episode_metrics": episode_metrics(episodes),
        "uncertainty": cluster_uncertainty(episodes, **payload["uncertainty"]),
    }
