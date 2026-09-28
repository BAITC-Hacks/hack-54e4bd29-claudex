"""Trusted registered object inference. Imported lazily by the organization worker."""

from __future__ import annotations

import hashlib
import importlib
import io
import json
import platform
import re
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from types import CodeType, FunctionType
from typing import Any, Protocol, cast

from app.business.forecasting.contracts import (
    ForecastEngineResult,
    ForecastMetricSet,
    ForecastPointResult,
    OrganizationForecastInput,
)
from app.business.forecasting.organization import OrganizationForecastService
from app.core.config import get_settings
from app.models.model_version import ModelVersion
from app.shared.analytics_contracts import AnalyticsFilter
from app.shared.analytics_data import QueryScope, RawTimeSeriesPoint


class VersionedModelObjects(Protocol):
    def get(self, key: str, version: str) -> bytes: ...


class MinioVersionedModelObjects:
    """Only the configured model bucket; no caller-selected bucket or local paths."""

    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def get(self, key: str, version: str) -> bytes:
        response = self._client.get_object(self._bucket, key, version_id=version)
        try:
            if response.headers.get("x-amz-version-id") != version:
                raise ValueError("OBJECT_VERSION_MISMATCH")
            data = response.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise ValueError("ARTIFACT_TOO_LARGE")
            return data
        finally:
            response.close()
            response.release_conn()


def _load_registered_estimator(payload: bytes) -> Callable:
    # Executable serialization is permitted ONLY after all registered hashes,
    # versions, report and review bindings have been verified below.
    import joblib
    from sklearn.ensemble import HistGradientBoostingRegressor

    estimator = joblib.load(io.BytesIO(payload))
    if type(estimator) is not HistGradientBoostingRegressor:
        raise ValueError("UNSUPPORTED_ESTIMATOR")
    if estimator.n_features_in_ != 12:
        raise ValueError("UNSUPPORTED_FEATURE_SCHEMA")
    return estimator.predict


def _runtime_implementation_sha256() -> str:
    """M's canonical four-file digest, plus loaded definitions (no source execution)."""
    hashes: dict[str, str] = {}
    for name in (
        "ml.monitoring",
        "ml.monitoring_contracts",
        "ml.evaluation.monitoring",
        "ml.evaluation.admission",
    ):
        module = importlib.import_module(name)
        if module.__file__ is None:
            raise ValueError("RUNTIME_IMPLEMENTATION_UNAVAILABLE")
        source = Path(module.__file__).read_bytes()
        hashes[name.replace(".", "/") + ".py"] = hashlib.sha256(source).hexdigest()
        compiled = compile(source, module.__file__, "exec", dont_inherit=True)
        for definition in compiled.co_consts:
            if not isinstance(definition, CodeType):
                continue
            actual = vars(module).get(definition.co_name)
            if isinstance(actual, type):
                for method in definition.co_consts:
                    if not isinstance(method, CodeType):
                        continue
                    implementation = vars(actual).get(method.co_name)
                    if isinstance(implementation, property):
                        implementation = implementation.fget
                    if isinstance(implementation, classmethod | staticmethod):
                        implementation = implementation.__func__
                    if (
                        not isinstance(implementation, FunctionType)
                        or implementation.__code__ != method
                    ):
                        raise ValueError("RUNTIME_IMPLEMENTATION_MISMATCH")
            elif not isinstance(actual, FunctionType) or actual.__code__ != definition:
                raise ValueError("RUNTIME_IMPLEMENTATION_MISMATCH")
    return hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _verify_runtime_dependencies(protocol: dict) -> None:
    import numpy
    import sklearn

    actual = {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scikit-learn": sklearn.__version__,
    }
    if protocol["dependency_versions"] != actual:
        raise ValueError("RUNTIME_DEPENDENCY_MISMATCH")


class RegisteredOrganizationEngine:
    def __init__(
        self, *, objects: VersionedModelObjects, loader: Callable | None = None
    ) -> None:
        self._objects = objects
        self._loader = loader or _load_registered_estimator

    def _verified(self, ref: dict[str, str]) -> bytes:
        key, version, digest = ref["key"], ref["version"], ref["sha256"]
        if (
            not key
            or key.startswith("/")
            or "\\" in key
            or ":" in key
            or ".." in key.split("/")
            or not version
            or version == "null"
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError("UNREGISTERED_OBJECT_REFERENCE")
        payload = self._objects.get(key, version)
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("REGISTERED_OBJECT_HASH_MISMATCH")
        return payload

    def _registration(
        self, model: ModelVersion, history: OrganizationForecastInput
    ) -> tuple[dict, dict, bytes]:
        from ml.monitoring_contracts import freeze_protocol

        runtime_digest = _runtime_implementation_sha256()
        reg = model.validation_config["organization_forecast_v1"]
        origin = history.history[-1].observed_on + timedelta(days=1)
        if (
            reg["schema_version"] != "organization-model-registry-v1"
            or reg["model_version"] != model.version
            or reg["model_type"] != "ML"
            or model.algorithm != "HistGradientBoostingRegressor"
            or reg["feature_schema_version"] != model.feature_schema_version
            or model.feature_schema_version != "hospital-referrals-direct7-v1"
            or str(history.hospital_id) not in reg["hospital_ids"]
            or not date.fromisoformat(reg["valid_from"])
            <= origin
            <= date.fromisoformat(reg["valid_through"]) - timedelta(days=6)
            or reg["artifact_sha256"] != reg["artifact"]["sha256"]
            or reg["protocol_sha256"] != reg["protocol"]["sha256"]
            or re.fullmatch(r"[0-9a-f]{64}", reg["code_sha256"]) is None
        ):
            raise ValueError("MODEL_REGISTRATION_MISMATCH")
        protocol = freeze_protocol(json.loads(self._verified(reg["protocol"]))).snapshot()
        if protocol["implementation_sha256"] != runtime_digest:
            raise ValueError("RUNTIME_IMPLEMENTATION_MISMATCH")
        _verify_runtime_dependencies(protocol)
        report, policy = reg["report"], reg["policy"]
        if (
            json.loads(self._verified(reg["report_object"])) != report
            or json.loads(self._verified(reg["policy_object"])) != policy
        ):
            raise ValueError("EVALUATION_OBJECT_MISMATCH")
        if (
            report["model_artifact_sha256"] != reg["artifact_sha256"]
            or report["protocol_sha256"] != reg["protocol_sha256"]
            or report["mapping_version"] != history.mapping_version
            or protocol["mapping_version"] != history.mapping_version
            or protocol["dataset_sha256"] != report["dataset_sha256"]
            or protocol["feature_schema"] != model.feature_schema_version
            or protocol["code_commit"] != reg["code_commit"]
            or protocol["implementation_sha256"] != reg["code_sha256"]
            or protocol["estimator"]["name"] != model.algorithm
            or protocol["policy_version"] != policy["version"]
            or model.metrics["mae"] != report["forecast_metrics"]["mae"]
            or model.baseline_metrics["mae"] != report["baseline_metrics"]["mae"]
        ):
            raise ValueError("PROVENANCE_MISMATCH")
        seal = report["sealed_period_evidence"]
        split = protocol["split"]
        if any(
            seal[key] != split[key] for key in ("train_end", "validation_end", "test_end")
        ):
            raise ValueError("SEALED_PROTOCOL_SPLIT_MISMATCH")
        test_start, test_end = (
            date.fromisoformat(seal["test_start"]),
            date.fromisoformat(seal["test_end"]),
        )
        if test_start != date.fromisoformat(split["validation_end"]) + timedelta(days=1):
            raise ValueError("SEALED_PROTOCOL_SPLIT_MISMATCH")
        if any(
            date.fromisoformat(period["start"]) <= test_end
            and date.fromisoformat(period["end"]) >= test_start
            for period in protocol["known_development_periods"]
        ):
            raise ValueError("TEST_PERIOD_PREVIOUSLY_VIEWED")
        for record in (
            policy["sign_off"],
            report["coverage_evidence"],
            report["sealed_period_evidence"],
        ):
            if (
                not isinstance(record, dict)
                or record.get("review_status") != "VERIFIED_EXTERNAL"
            ):
                raise ValueError("EXTERNAL_REVIEW_MISSING")
            ref = reg["review_objects"].get(record["evidence_ref"])
            if ref is None or ref["sha256"] != record["evidence_sha256"]:
                raise ValueError("EXTERNAL_REVIEW_MISSING")
            expected = {k: v for k, v in record.items() if k != "evidence_sha256"}
            if json.loads(self._verified(ref)) != expected:
                raise ValueError("EXTERNAL_REVIEW_MISMATCH")
        return reg, protocol, self._verified(reg["artifact"])

    def admission(
        self, model: ModelVersion, history: OrganizationForecastInput
    ) -> dict[str, object]:
        from ml.evaluation.admission import evaluate_admission

        try:
            registration = model.validation_config["organization_forecast_v1"]
            decision = evaluate_admission(registration["report"], registration["policy"])
            if decision["status"] != "PASS":
                return decision
            self._registration(model, history)
            return decision
        except (KeyError, TypeError, IndexError) as exc:
            raise ValueError("INVALID_REGISTRATION") from exc

    def predict(
        self, model: ModelVersion, history: OrganizationForecastInput
    ) -> ForecastEngineResult:
        from ml.evaluation.admission import evaluate_admission
        from ml.evaluation.monitoring import forecast_at
        from ml.monitoring_contracts import (
            AggregateSeries,
            DailyObservation,
            canonical_sha256,
        )

        try:
            reg, protocol, payload = self._registration(model, history)
            decision = evaluate_admission(reg["report"], reg["policy"])
            if decision["status"] != "PASS":
                raise ValueError("MODEL_NOT_ADMITTED")
            predictor = self._loader(payload)
            series = AggregateSeries(
                str(history.hospital_id),
                tuple(
                    DailyObservation(p.observed_on, p.count, history.coverage_complete)
                    for p in history.history
                ),
                history.history[0].observed_on,
                canonical_sha256(
                    {
                        "hospital_id": str(history.hospital_id),
                        "mapping_version": history.mapping_version,
                        "delivery_watermark": history.delivery_watermark,
                        "history": [
                            [p.observed_on.isoformat(), p.count] for p in history.history
                        ],
                    }
                ),
            )
            origin = history.history[-1].observed_on
            prediction = forecast_at((series,), origin, predictor)
            if prediction["status"] != "PASS":
                raise ValueError("INSUFFICIENT_HISTORY")
            values = prediction["forecasts"][str(history.hospital_id)]
            baseline = protocol["baseline_selection"]["selected"]
            last_week = [float(p.count) for p in history.history[-7:]]
            baseline_values = (
                last_week if baseline == "weekly_naive" else [mean(last_week)] * 7
            )
            return ForecastEngineResult(
                organization_evidence={
                    "schema_version": "organization-alert-policy-v1",
                    "episode_policy": protocol["episode_policy"],
                    "episode_anchor": (
                        date.fromisoformat(protocol["split"]["validation_end"])
                        + timedelta(days=1)
                    ).isoformat(),
                    "protocol_sha256": reg["protocol_sha256"],
                },
                generated_at=history.as_of,
                input_period_start=history.history[0].observed_on,
                input_period_end=origin,
                training_rows=model.training_rows,
                feature_schema_version=model.feature_schema_version,
                selected_model=model.algorithm,
                selected_model_type="ML",
                model_version=model.version,
                mlflow_run_id=model.mlflow_run_id,
                metrics=ForecastMetricSet(**model.metrics),
                strongest_baseline=baseline,
                baseline_metrics=ForecastMetricSet(**model.baseline_metrics),
                validation_folds=(),
                candidate_metrics=(),
                selection_rationale=model.selection_rationale,
                points=tuple(
                    ForecastPointResult(
                        origin + timedelta(days=i + 1), value, float(baseline_values[i])
                    )
                    for i, value in enumerate(values)
                ),
            )
        except (KeyError, TypeError, IndexError) as exc:
            raise ValueError("INVALID_REGISTERED_INFERENCE") from exc


def build_organization_forecast_service() -> OrganizationForecastService:
    settings = get_settings()
    if not settings.organization_forecast_enabled:
        return OrganizationForecastService()
    from minio import Minio

    from app.business.signals.policy import SignalPolicy
    from app.database.postgres import get_session_factory
    from app.repositories.organization_forecasts import (
        SqlAlchemyOrganizationForecastRepository,
    )

    objects = MinioVersionedModelObjects(
        Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        ),
        settings.minio_bucket_models,
    )
    return OrganizationForecastService(
        enabled=True,
        repository=SqlAlchemyOrganizationForecastRepository(
            get_session_factory(),
            history_repository=LazyApprovedOrganizationHistory(),
        ),
        engine=RegisteredOrganizationEngine(objects=objects),
        policy=SignalPolicy(
            rule_version=settings.signal_rule_version,
            warning_percent=settings.signal_warning_percent,
            high_percent=settings.signal_high_percent,
            critical_percent=settings.signal_critical_percent,
            freshness_max_age_hours={
                "REFERRALS": settings.signal_referrals_max_age_hours
            },
        ),
    )


class LazyApprovedOrganizationHistory:
    """No ClickHouse connection until the PostgreSQL publication gate is locked."""

    def referral_timeseries(
        self, filters: AnalyticsFilter, scope: QueryScope
    ) -> tuple[RawTimeSeriesPoint, ...]:
        from app.database.clickhouse import get_client
        from app.repositories.clickhouse_analytics import (
            ClickHouseAnalyticsRepository,
            ClickHouseQueryClient,
        )

        return ClickHouseAnalyticsRepository(
            cast(ClickHouseQueryClient, get_client())
        ).referral_timeseries(filters, scope)
