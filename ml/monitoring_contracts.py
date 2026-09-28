"""Framework-neutral, immutable approved-aggregate evaluation contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta


def canonical_json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Expected finite JSON provenance") from exc


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_sha256(value: object) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected lowercase SHA256 hash")


def require_text(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected nonempty text")


def require_day(value: object) -> None:
    if type(value) is not date:
        raise ValueError("Expected a date without time")


@dataclass(frozen=True)
class DailyObservation:
    day: date
    value: int | None
    delivery_complete: bool

    def __post_init__(self) -> None:
        require_day(self.day)
        if type(self.delivery_complete) is not bool:
            raise ValueError("delivery_complete must be boolean")
        if self.delivery_complete:
            if type(self.value) is not int or self.value < 0:
                raise ValueError("Complete day requires a nonnegative count")
        elif self.value is not None:
            raise ValueError("Incomplete day is UNKNOWN, not a count")


@dataclass(frozen=True)
class SplitSpec:
    train_end: date
    validation_end: date
    test_end: date
    horizon_days: int = 7

    def __post_init__(self) -> None:
        for value in (self.train_end, self.validation_end, self.test_end):
            require_day(value)
        if not self.train_end < self.validation_end < self.test_end:
            raise ValueError("Split dates must be strictly increasing")
        if type(self.horizon_days) is not int or self.horizon_days != 7:
            raise ValueError("This protocol requires seven-day episodes")


def label_within_training(origin: date, split: SplitSpec) -> bool:
    require_day(origin)
    return origin + timedelta(days=split.horizon_days) <= split.train_end


@dataclass(frozen=True)
class AggregateManifest:
    schema_version: str
    period_start: date
    period_end: date
    confirmed_complete_through: date | None
    organizations: tuple[str, ...]
    mapping_version: str
    mapping_available_on: date
    mapping_approval_ref: str
    delivery_evidence_ref: str
    aggregate_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != "approved-aggregate-v1":
            raise ValueError("Unsupported aggregate schema")
        for day in (self.period_start, self.period_end, self.mapping_available_on):
            require_day(day)
        if self.period_start > self.period_end:
            raise ValueError("Invalid aggregate period")
        if self.confirmed_complete_through is not None:
            require_day(self.confirmed_complete_through)
            if self.confirmed_complete_through > self.period_end:
                raise ValueError("Completeness watermark exceeds manifest period")
        if (
            type(self.organizations) is not tuple
            or not self.organizations
            or len(set(self.organizations)) != len(self.organizations)
        ):
            raise ValueError("An immutable approved reporting population is required")
        for value in (
            *self.organizations,
            self.mapping_version,
            self.mapping_approval_ref,
            self.delivery_evidence_ref,
        ):
            require_text(value)
        require_sha256(self.aggregate_sha256)

    def snapshot(self) -> dict:
        from dataclasses import asdict

        payload = asdict(self)
        for key in (
            "period_start",
            "period_end",
            "mapping_available_on",
            "confirmed_complete_through",
        ):
            payload[key] = payload[key].isoformat() if payload[key] is not None else None
        payload["organizations"] = sorted(payload["organizations"])
        return payload

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.snapshot())


@dataclass(frozen=True)
class AggregateSeries:
    organization_id: str
    observations: tuple[DailyObservation, ...]
    mapping_available_on: date
    manifest_sha256: str

    def __post_init__(self) -> None:
        require_text(self.organization_id)
        require_day(self.mapping_available_on)
        require_sha256(self.manifest_sha256)
        if type(self.observations) is not tuple or not self.observations:
            raise ValueError("Expected immutable daily observations")
        for previous, current in zip(
            self.observations, self.observations[1:], strict=False
        ):
            if current.day != previous.day + timedelta(days=1):
                raise ValueError("Observations must be contiguous and unique")


@dataclass(frozen=True)
class TrainingSample:
    organization_id: str
    origin: date
    features: tuple[tuple[float, ...], ...]
    targets: tuple[int, ...]


@dataclass(frozen=True)
class FrozenProtocol:
    canonical_json: str

    def snapshot(self) -> dict:
        return json.loads(self.canonical_json)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


def freeze_protocol(payload: dict) -> FrozenProtocol:
    required = {
        "schema_version",
        "aggregate_manifest_sha256",
        "dataset_sha256",
        "source_manifest_hashes",
        "split",
        "timezone",
        "feature_schema",
        "mapping_version",
        "code_commit",
        "implementation_sha256",
        "estimator",
        "random_seed",
        "dependency_versions",
        "eligibility",
        "episode_policy",
        "baseline_selection",
        "policy_version",
        "uncertainty",
        "known_development_periods",
    }
    if type(payload) is not dict or set(payload) != required:
        raise ValueError("Protocol requires complete provenance and no unknown keys")
    if payload["schema_version"] != "monitoring-evaluation-v2":
        raise ValueError("Unsupported protocol version")
    require_sha256(payload["aggregate_manifest_sha256"])
    require_sha256(payload["dataset_sha256"])
    require_sha256(payload["implementation_sha256"])
    hashes = payload["source_manifest_hashes"]
    if type(hashes) is not list or not hashes:
        raise ValueError("Source manifest hashes required")
    for digest in hashes:
        require_sha256(digest)
    try:
        split = payload["split"]
        SplitSpec(
            date.fromisoformat(split["train_end"]),
            date.fromisoformat(split["validation_end"]),
            date.fromisoformat(split["test_end"]),
            split["horizon_days"],
        )
        # Aggregates are already supplier-local dates; no timestamp conversion.
        if payload["timezone"] not in ("UTC", "Asia/Qyzylorda", "Asia/Almaty"):
            raise ValueError("Unsupported supplier timezone")
        if re.fullmatch(r"[0-9a-f]{40}", payload["code_commit"]) is None:
            raise ValueError("Full code commit required")
        for key in ("feature_schema", "mapping_version", "policy_version"):
            require_text(payload[key])
        if payload["feature_schema"] != "hospital-referrals-direct7-v1":
            raise ValueError("Unsupported feature schema")
        estimator = payload["estimator"]
        require_text(estimator["name"])
        required_parameters = {
            "categorical_features",
            "early_stopping",
            "interaction_cst",
            "l2_regularization",
            "learning_rate",
            "loss",
            "max_bins",
            "max_depth",
            "max_features",
            "max_iter",
            "max_leaf_nodes",
            "min_samples_leaf",
            "monotonic_cst",
            "n_iter_no_change",
            "quantile",
            "random_state",
            "scoring",
            "tol",
            "validation_fraction",
            "verbose",
            "warm_start",
        }
        if (
            estimator["name"] != "HistGradientBoostingRegressor"
            or type(estimator["parameters"]) is not dict
            or not required_parameters <= set(estimator["parameters"])
        ):
            raise ValueError("Explicit estimator parameters required")
        if (
            type(payload["random_seed"]) is not int
            or estimator["parameters"].get("random_state") != payload["random_seed"]
        ):
            raise ValueError("Explicit consistent random seed required")
        versions = payload["dependency_versions"]
        for key in ("python", "numpy", "scikit-learn"):
            require_text(versions[key])
        eligibility = payload["eligibility"]
        for key, minimum in (
            ("minimum_training_days", 28),
            ("minimum_training_total", 0),
        ):
            if type(eligibility[key]) is not int or eligibility[key] < minimum:
                raise ValueError("Invalid training eligibility")
        episode = payload["episode_policy"]
        if episode != {
            "version": "referral-growth-v1",
            "window_days": 7,
            "reference_days": 28,
            "min_reference_total": 20,
            "min_extra_referrals": 10,
            "growth_threshold_percent": 20,
        }:
            raise ValueError("Only frozen existing growth-label policy supported")
        selection = payload["baseline_selection"]
        if selection["selected_on"] != "validation" or selection["selected"] not in (
            "weekly_naive",
            "mean7",
        ):
            raise ValueError("Baseline must be selected on validation")
        for key, minimum in (
            ("seed", 0),
            ("resamples", 100),
            ("min_organizations", 2),
            ("min_time_blocks", 4),
        ):
            if (
                type(payload["uncertainty"][key]) is not int
                or payload["uncertainty"][key] < minimum
            ):
                raise ValueError("Invalid cluster uncertainty settings")
        periods = payload["known_development_periods"]
        if not periods or not any(
            p["start"] <= "2025-01-01" and p["end"] >= "2025-03-31" for p in periods
        ):
            raise ValueError("Q1 2025 development provenance required")
        for period in periods:
            if date.fromisoformat(period["start"]) > date.fromisoformat(period["end"]):
                raise ValueError("Invalid development period")
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed protocol provenance") from exc
    return FrozenProtocol(canonical_json(payload))
