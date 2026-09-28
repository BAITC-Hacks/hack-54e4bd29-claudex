"""Read-only verification of a persisted synthetic weekly-naive forecast.

Run inside the isolated phase8 worker with its existing PostgreSQL/ClickHouse
connections. Prints aggregate evidence only; never emits records or secrets.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

from ml.contracts import ValidationFold
from ml.validation import rolling_origin_folds


def weekly_naive_errors(
    observations: Sequence[tuple[date, float]],
    folds: Sequence[ValidationFold],
) -> list[tuple[date, float, float]]:
    """Reconstruct validation pairs using only the preceding training week."""
    pairs: list[tuple[date, float, float]] = []
    for fold in folds:
        assert fold.train_end < fold.validation_start
        assert len(fold.validation_indices) <= 7
        train_last = fold.train_indices[-1]
        for index in fold.validation_indices:
            prior_week = index - 7
            assert prior_week <= train_last, "A validation target entered its own input"
            pairs.append(
                (
                    observations[index][0],
                    observations[index][1],
                    observations[prior_week][1],
                )
            )
    if len({day for day, _, _ in pairs}) != len(pairs):
        raise AssertionError("Validation windows overlap")
    return pairs


def verify(forecast_id: UUID) -> dict[str, object]:
    """Compare independently reconstructed pairs to saved PostgreSQL evidence."""
    from app.core.config import get_settings
    from app.database.clickhouse import get_client
    from app.database.postgres import get_session_factory
    from app.models.analytics import Forecast
    from app.models.data_import import DataImport
    from app.models.model_version import ModelVersion
    from app.repositories.clickhouse_forecasting import (
        ClickHouseQueryClient,
        ClickHouseReferralHistoryRepository,
    )
    from app.repositories.forecast_metadata import SqlAlchemyForecastMetadataRepository

    session_factory = get_session_factory()
    metadata = SqlAlchemyForecastMetadataRepository(session_factory)
    watermark = metadata.referral_watermark()
    with session_factory() as session:
        forecast = session.get(Forecast, forecast_id)
        if forecast is None or forecast.selected_model != "weekly_naive":
            raise ValueError("Expected persisted weekly_naive forecast")
        model = session.get(ModelVersion, forecast.model_version_id)
        imports = [session.get(DataImport, item) for item in watermark.import_ids]
        if model is None or any(
            item is None or not item.file_name.lower().startswith("synthetic")
            for item in imports
        ):
            raise ValueError("Synthetic-only model provenance was not confirmed")
        if forecast.dataset_watermark != watermark.as_dict():
            raise ValueError("Forecast watermark differs from published imports")
        saved_folds = list(forecast.validation_folds)
        saved_mae = float(forecast.validation_metrics["mae"])
        saved_baseline_mae = float(forecast.baseline_metrics["mae"])
        if forecast.metric_value is None:
            raise ValueError("Forecast MAE is absent")
        metric_value = float(forecast.metric_value)
        rows_loaded = sum(item.rows_loaded for item in imports if item is not None)
        model_version = model.version
        if forecast.model_version != model_version:
            raise AssertionError("Forecast and registered model versions differ")
        train_end = model.training_period_end
        forecast_start = forecast.forecast_start
        forecast_end = forecast.forecast_end
        horizon = forecast.horizon_days
    history = ClickHouseReferralHistoryRepository(
        cast(ClickHouseQueryClient, get_client()),
        import_ids_provider=lambda: watermark.import_ids,
    ).daily_global()
    if sum(item.count for item in history) != rows_loaded:
        raise AssertionError("Published import rows differ from ClickHouse daily counts")
    observations = tuple((item.observed_on, float(item.count)) for item in history)
    folds = rolling_origin_folds(
        tuple(day for day, _ in observations),
        horizon=horizon,
        min_train_size=get_settings().forecast_min_train_days,
    )
    if len(folds) != len(saved_folds):
        raise AssertionError("Saved and reconstructed fold counts differ")
    for fold, saved in zip(folds, saved_folds, strict=True):
        if (
            saved["train_end"] != fold.train_end.isoformat()
            or saved["validation_start"] != fold.validation_start.isoformat()
            or saved["validation_end"] != fold.validation_end.isoformat()
        ):
            raise AssertionError("Saved fold boundaries differ from source history")
        fold_pairs = weekly_naive_errors(observations, (fold,))
        fold_mae = sum(
            abs(actual - predicted) for _, actual, predicted in fold_pairs
        ) / len(fold_pairs)
        if not math.isclose(fold_mae, saved["metrics"]["mae"], abs_tol=1e-9):
            raise AssertionError("Saved fold MAE differs from observations")
    pairs = weekly_naive_errors(observations, folds)
    mae = sum(abs(actual - predicted) for _, actual, predicted in pairs) / len(pairs)
    if not all(
        math.isclose(mae, value, abs_tol=1e-6)
        for value in (saved_mae, saved_baseline_mae, metric_value)
    ):
        raise AssertionError("Persisted MAE differs from validation pairs")
    if (
        train_end != history[-1].observed_on
        or forecast_start != history[-1].observed_on + timedelta(days=1)
        or forecast_end != history[-1].observed_on + timedelta(days=horizon)
    ):
        raise AssertionError("Training cutoff or future forecast period differs")
    return {
        "forecast_id": str(forecast_id),
        "model_version": model_version,
        "selected_model": "weekly_naive",
        "source_rows_loaded": rows_loaded,
        "history_days": len(history),
        "folds": len(folds),
        "validation_pairs": len(pairs),
        "first_train_end": folds[0].train_end.isoformat(),
        "first_validation_start": folds[0].validation_start.isoformat(),
        "last_validation_end": folds[-1].validation_end.isoformat(),
        "final_training_cutoff": train_end.isoformat(),
        "forecast_start": forecast_start.isoformat(),
        "forecast_end": forecast_end.isoformat(),
        "recomputed_mae_referrals_per_day": mae,
        "saved_mae_referrals_per_day": saved_mae,
        "saved_baseline_mae_referrals_per_day": saved_baseline_mae,
        "chronological_no_leakage": True,
        "synthetic_only": True,
    }


def verify_source_fixture(project_dir: Path, expected_mae: float) -> dict[str, object]:
    """Recompute MAE from hashed synthetic CSVs when Docker is unavailable."""
    metadata = json.loads((project_dir / "manifest.json").read_text(encoding="utf-8"))
    if (
        not project_dir.name.startswith("phase8-")
        or metadata.get("project") != project_dir.name
        or metadata.get("dataset") != "synthetic-only"
    ):
        raise ValueError("Only a phase8 synthetic project is supported")
    directories = (project_dir / "source-empty", project_dir / "source-forecast")
    manifest_names = ("manifest-REFERRALS.json", "manifest-REFERRALS-forecast-demo.json")
    counts: Counter[date] = Counter()
    total = 0
    for directory, name in zip(directories, manifest_names, strict=True):
        manifest = json.loads((directory / name).read_text(encoding="utf-8"))
        synthetic_delivery = manifest["delivery_id"].startswith("phase8-synthetic-")
        if manifest["dataset_type"] != "REFERRALS" or not synthetic_delivery:
            raise ValueError("Non-synthetic delivery")
        referral_dir = directory / "Направления на плановую госпитализацию в стационары"
        sources = list(referral_dir.glob("*.csv"))
        if len(sources) != 1:
            # The first bootstrap source may also hold a failed, unpublished
            # fixture attempt; inspect only the hash named in this manifest.
            sources = [
                source
                for source in sources
                if hashlib.sha256(source.read_bytes()).hexdigest()
                in manifest["file_hashes"]
            ]
        if len(sources) != 1:
            raise ValueError("Manifest does not identify exactly one synthetic CSV")
        source = sources[0]
        if hashlib.sha256(source.read_bytes()).hexdigest() not in manifest["file_hashes"]:
            raise ValueError("Synthetic source hash mismatch")
        rows_in_file = 0
        with source.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                counts[date.fromisoformat(row["registration_dt"][:10])] += 1
                total += 1
                rows_in_file += 1
        if rows_in_file != manifest["expected_rows"]:
            raise AssertionError("Manifest row count mismatch")
    days = [counts[date(2025, 1, 1) + timedelta(days=offset)] for offset in range(90)]
    if sum(days) != total or any(count == 0 for count in days):
        raise AssertionError("Expected complete, two-part synthetic history")
    observations = tuple(
        (date(2025, 1, 1) + timedelta(days=index), float(count))
        for index, count in enumerate(days)
    )
    folds = rolling_origin_folds(
        tuple(day for day, _ in observations), horizon=7, min_train_size=42
    )
    pairs = weekly_naive_errors(observations, folds)
    mae = sum(abs(actual - predicted) for _, actual, predicted in pairs) / len(pairs)
    if not math.isclose(mae, expected_mae, abs_tol=1e-9):
        raise AssertionError("Source-pair MAE differs from the API value")
    return {
        "verification_source": "hashed_synthetic_csv",
        "rows": total,
        "history_days": len(days),
        "folds": len(folds),
        "validation_pairs": len(pairs),
        "first_train_end": folds[0].train_end.isoformat(),
        "first_validation_start": folds[0].validation_start.isoformat(),
        "last_validation_end": folds[-1].validation_end.isoformat(),
        "recomputed_mae_referrals_per_day": mae,
        "matches_api_mae": True,
        "chronological_no_leakage": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--forecast-id", type=UUID)
    target.add_argument("--project-dir", type=Path)
    parser.add_argument("--expected-mae", type=float)
    args = parser.parse_args()
    if args.project_dir is not None:
        if args.expected_mae is None:
            parser.error("--expected-mae is required with --project-dir")
        result = verify_source_fixture(args.project_dir, args.expected_mae)
    else:
        result = verify(args.forecast_id)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
