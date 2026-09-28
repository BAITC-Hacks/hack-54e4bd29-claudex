"""MLflow experiment and selected-model registration for Phase 5A."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import mlflow
import mlflow.pyfunc
import pandas as pd
from mlflow.models import infer_signature
from mlflow.pyfunc import PythonModel

from ml.baselines import BASELINES
from ml.contracts import TrainingResult
from ml.dataset import feature_rows
from ml.forecasting.model import HistGradientBoostingForecaster

FEATURE_COLUMNS = [
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_7",
    "rolling_mean_7",
    "rolling_std_7",
    "day_of_week",
]


@dataclass(frozen=True, slots=True)
class TrackedModel:
    run_id: str
    model_version: str
    registry_version: str


class ForecastPyFuncModel(PythonModel):
    """Portable one-step selected candidate; recursion stays in orchestration."""

    def __init__(self, model_name: str, estimator: Any | None = None) -> None:
        self.model_name = model_name
        self.estimator = estimator

    def predict(
        self,
        context: Any,
        model_input: pd.DataFrame,
        params: dict[str, Any] | None = None,
    ) -> Any:
        del context, params
        if self.model_name == "naive_last":
            return model_input["lag_1"].to_numpy()
        if self.model_name == "weekly_naive":
            return model_input["lag_7"].to_numpy()
        if self.model_name == "moving_average_7":
            return model_input["rolling_mean_7"].to_numpy()
        if self.estimator is None:
            raise RuntimeError("Selected ML estimator is missing")
        return self.estimator.predict(model_input[FEATURE_COLUMNS].to_numpy())


class MlflowExperimentTracker:
    def __init__(
        self,
        *,
        tracking_uri: str,
        experiment_name: str,
        registered_model_name: str,
    ) -> None:
        self._tracking_uri = tracking_uri
        self._experiment_name = experiment_name
        self._registered_model_name = registered_model_name

    def _selected_model(self, result: TrainingResult) -> ForecastPyFuncModel:
        selected = result.selection.selected.model_name
        if result.selection.ml_selected:
            model = HistGradientBoostingForecaster()
            model.fit(
                [(item.observed_on, item.value) for item in result.dataset.observations]
            )
            return ForecastPyFuncModel(selected, model.estimator)
        if selected not in {item.name for item in BASELINES}:
            raise ValueError(f"Unknown selected baseline: {selected}")
        return ForecastPyFuncModel(selected)

    def track(self, result: TrainingResult) -> TrackedModel:
        mlflow.set_tracking_uri(self._tracking_uri)
        mlflow.set_experiment(self._experiment_name)
        with mlflow.start_run() as active:
            run_id = active.info.run_id
            mlflow.log_params(
                {
                    "model_type": result.selection.selected.model_type,
                    "selected_model": result.selection.selected.model_name,
                    "model_version": (
                        "referrals-global-"
                        f"{result.dataset.metadata.period_end:%Y%m%d}-{run_id[:8]}"
                    ),
                    "training_start": result.dataset.metadata.period_start.isoformat(),
                    "training_end": result.dataset.metadata.period_end.isoformat(),
                    "forecast_horizon": len(result.forecast),
                    "feature_schema_version": (
                        result.dataset.metadata.feature_schema_version
                    ),
                    "dataset_watermark": result.dataset.metadata.source_watermark,
                    "training_row_count": result.dataset.metadata.row_count,
                    "validation_folds": len(result.selection.selected.folds),
                    "validation_strategy": "expanding_window_rolling_origin",
                }
            )
            selected = result.selection.selected.overall
            mlflow.log_metric("selected_mae", selected.mae)
            if selected.wape is not None:
                mlflow.log_metric("selected_wape", selected.wape)
            mlflow.log_metric("selected_rmse", selected.rmse)
            for candidate in result.evaluations:
                prefix = candidate.model_name
                mlflow.log_metric(f"{prefix}_mae", candidate.overall.mae)
                if candidate.overall.wape is not None:
                    mlflow.log_metric(f"{prefix}_wape", candidate.overall.wape)
                mlflow.log_metric(f"{prefix}_rmse", candidate.overall.rmse)
                for fold in candidate.folds:
                    fold_prefix = f"{prefix}_fold_{fold.fold.index}"
                    mlflow.log_metric(f"{fold_prefix}_mae", fold.metrics.mae)
                    if fold.metrics.wape is not None:
                        mlflow.log_metric(f"{fold_prefix}_wape", fold.metrics.wape)
                    mlflow.log_metric(f"{fold_prefix}_rmse", fold.metrics.rmse)
            mlflow.log_dict(
                {
                    "dataset": asdict(result.dataset.metadata),
                    "selection_rationale": result.selection.rationale,
                    "candidates": [asdict(item) for item in result.evaluations],
                },
                "evaluation.json",
            )
            rows = feature_rows(result.dataset.observations)
            input_example = pd.DataFrame([rows[-1].features], columns=FEATURE_COLUMNS)
            pyfunc_model = self._selected_model(result)
            prediction_example = pyfunc_model.predict(None, input_example)
            mlflow.pyfunc.log_model(
                artifact_path="selected_model",
                python_model=pyfunc_model,
                input_example=input_example,
                signature=infer_signature(input_example, prediction_example),
            )
            model_uri = f"runs:/{run_id}/selected_model"
            registered = mlflow.register_model(model_uri, self._registered_model_name)
            model_version = (
                "referrals-global-"
                f"{result.dataset.metadata.period_end:%Y%m%d}-{run_id[:8]}"
            )
            return TrackedModel(run_id, model_version, str(registered.version))
