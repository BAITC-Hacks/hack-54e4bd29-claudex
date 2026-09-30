"""Read-only persisted forecast check, self-contained for worker stdin execution."""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta
from typing import Any
from uuid import UUID


def assert_persisted_contract(record: dict[str, Any]) -> None:
    """Reject an incomplete or non-global saved forecast without fitting numbers."""
    if record["target"] != "DAILY_REFERRAL_COUNT" or record["scope_type"] != "GLOBAL":
        raise AssertionError("Persisted forecast target or scope mismatch")
    if record["horizon_days"] != 7:
        raise AssertionError("Persisted forecast horizon mismatch")
    if record["input_period_end"] != "2025-03-31":
        raise AssertionError("Persisted forecast historical cutoff mismatch")
    start = date(2025, 4, 1)
    expected_points = [
        (start + timedelta(days=offset)).isoformat() for offset in range(7)
    ]
    if (
        record["point_dates"] != expected_points
        or record["forecast_start"] != expected_points[0]
        or record["forecast_end"] != expected_points[-1]
    ):
        raise AssertionError("Persisted forecast point period mismatch")
    if not record["model_version"]:
        raise AssertionError("Persisted forecast model version missing")
    for field in ("validation_mae", "baseline_mae"):
        value = record[field]
        if not isinstance(value, float | int) or not math.isfinite(value) or value < 0:
            raise AssertionError("Persisted forecast MAE missing or invalid")


def assert_summary_mae(summary: object, full_precision: object) -> None:
    """Numeric(18,6) summary may differ by at most half a stored unit."""
    if summary is None or full_precision is None or not math.isclose(
        float(summary), float(full_precision), rel_tol=0, abs_tol=5e-7
    ):
        raise AssertionError("Persisted summary MAE differs from validation metrics")


def verify_forecast_db(forecast_id: UUID) -> dict[str, object]:
    """Compare forecast, points, model, and published referral import in PostgreSQL."""
    from app.database.postgres import get_session_factory
    from app.models.analytics import Forecast
    from app.models.data_import import DataImport
    from app.models.enums import DataImportStatus, ForecastStatus
    from app.models.forecast_point import ForecastPoint
    from app.models.model_version import ModelVersion
    from sqlalchemy import select

    with get_session_factory()() as session:
        forecast = session.get(Forecast, forecast_id)
        if forecast is None or forecast.status != ForecastStatus.VALID:
            raise ValueError("Expected a persisted VALID local referral forecast")
        model = session.get(ModelVersion, forecast.model_version_id)
        if model is None or model.version != forecast.model_version:
            raise AssertionError("Forecast model registration mismatch")
        if model.training_period_end != date(2025, 3, 31):
            raise AssertionError("Model training cutoff mismatch")
        if forecast.validation_metrics != model.metrics:
            raise AssertionError("Forecast validation metrics differ from model")
        if forecast.baseline_metrics != model.baseline_metrics:
            raise AssertionError("Forecast baseline metrics differ from model")
        if forecast.dataset_watermark != model.dataset_watermark:
            raise AssertionError("Forecast dataset watermark differs from model")
        points = list(session.scalars(
            select(ForecastPoint)
            .where(ForecastPoint.forecast_id == forecast_id)
            .order_by(ForecastPoint.forecast_date)
        ))
        record = {
            "target": forecast.target,
            "scope_type": str(forecast.scope_type),
            "horizon_days": forecast.horizon_days,
            "input_period_end": forecast.input_period_end.date().isoformat(),
            "forecast_start": forecast.forecast_start.isoformat()
            if forecast.forecast_start else None,
            "forecast_end": forecast.forecast_end.isoformat()
            if forecast.forecast_end else None,
            "model_version": forecast.model_version,
            "validation_mae": forecast.validation_metrics.get("mae"),
            "baseline_mae": forecast.baseline_metrics.get("mae"),
            "point_dates": [point.forecast_date.isoformat() for point in points],
        }
        assert_persisted_contract(record)
        assert_summary_mae(forecast.metric_value, record["validation_mae"])
        assert_summary_mae(forecast.baseline_metric_value, record["baseline_mae"])
        import_ids = forecast.dataset_watermark.get("import_ids", [])
        imports = [session.get(DataImport, UUID(value)) for value in import_ids]
        if len(imports) != 1 or any(
            item is None
            or item.dataset_type != "REFERRALS"
            or item.status != DataImportStatus.COMPLETED
            or not item.file_name.lower().startswith("synthetic-local-demo")
            for item in imports
        ):
            raise AssertionError("Forecast provenance is not one published local CSV")
        referral_import = imports[0]
        if referral_import is None:
            raise AssertionError("Referral import missing")
        if forecast.dataset_watermark.get("file_hashes") != [referral_import.file_hash]:
            raise AssertionError("Forecast source hash differs from imported CSV")
        return {
            "forecast_id": str(forecast_id),
            "target": record["target"],
            "scope_type": record["scope_type"],
            "model_version": record["model_version"],
            "selected_model": forecast.selected_model,
            "baseline_model": forecast.baseline_model,
            "source_rows_loaded": referral_import.rows_loaded,
            "point_dates": record["point_dates"],
            "validation_mae_referrals_per_day": record["validation_mae"],
            "baseline_mae_referrals_per_day": record["baseline_mae"],
            "validation_folds": len(forecast.validation_folds),
            "persisted": "PASS",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast-id", required=True, type=UUID)
    args = parser.parse_args()
    print(json.dumps(verify_forecast_db(args.forecast_id), sort_keys=True))


if __name__ == "__main__":
    main()
