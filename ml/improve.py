"""Bounded experiments selected on validation only; reused test is labelled."""

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from ml.monitoring import alert_for, assess, metrics, predict, samples
from ml.risk import (
    RISK_FEATURES,
    MonitoringModel,
    candidates,
    choose_threshold,
    classification,
    growth_label,
    risk_samples,
    scores,
)


def evaluated(estimator, series, dates, origins, threshold=None):
    y, p, names = [], [], []
    folds = []
    for origin in origins:
        s = scores(estimator, series, dates, origin)
        a = [growth_label(v, origin) for v in series.values()]
        b = list(s.values())
        y.extend(a)
        p.extend(b)
        names.extend(series)
        folds.append({"as_of": dates[origin], "actual": a, "scores": b})
    if threshold is None:
        threshold, result = choose_threshold(y, p)
    else:
        result = classification(y, np.asarray(p) >= threshold)
    return threshold, result, y, p, names, folds


def main():
    root = Path("data/monitoring")
    old = Path("data/monitoring-v1")
    if not (old / "bundle.json").exists():
        from ml.monitoring import train

        train(Path("data/incoming"), old)
    root.mkdir(parents=True, exist_ok=True)
    bundle = json.loads((old / "bundle.json").read_text())
    report = bundle["report"]
    runtime = bundle["runtime"]
    dates = runtime["dates"]
    series = runtime["series"]
    train_end = dates.index(report["train_end"])
    valid_end = runtime["start_origin"]
    old_model = joblib.load(old / "model.joblib")["model"]
    # Verify the exact downloaded bytes supporting the cached aggregates.
    for file in report["source"]["files"]:
        with (Path("data/incoming") / file["name"]).open("rb") as f:
            assert hashlib.file_digest(f, "sha256").hexdigest() == file["sha256"]
    x, y = risk_samples(series, dates, train_end)
    trials = []
    trained = {}
    for name, model in candidates().items():
        model.fit(x, y)
        trained[name] = model
        threshold, m, *_ = evaluated(model, series, dates, [train_end, train_end + 7])
        trials.append(
            {
                "name": name,
                "threshold": threshold,
                "validation": m,
                "parameters": {
                    k: repr(v) for k, v in model.get_params(deep=True).items()
                },
            }
        )
        print(trials[-1], flush=True)
    best_hgb = max(
        [t for t in trials if t["name"].startswith("hgb")],
        key=lambda t: t["validation"]["f2"],
    )
    ensemble = [trained[best_hgb["name"]], trained["logistic_True"]]
    trained["ensemble"] = ensemble
    t, m, *_ = evaluated(ensemble, series, dates, [train_end, train_end + 7])
    trials.append({"name": "ensemble", "threshold": t, "validation": m})
    allowed = [
        t
        for t in trials
        if t["validation"]["precision_percent"] >= 40
        and t["validation"]["alert_rate_percent"] <= 25
    ]
    winner = max(
        allowed or trials,
        key=lambda t: (
            t["validation"]["f2"],
            t["validation"]["precision_percent"],
            -t["validation"]["alert_rate_percent"],
        ),
    )
    detector = trained[winner["name"]]
    threshold = winner["threshold"]
    _, _, vy, vp, vnames, vfolds = evaluated(
        detector, series, dates, [train_end, train_end + 7], threshold
    )
    # Segment-specific thresholds use the same aggregate constraints.
    groups = {
        name: (
            "small"
            if np.mean(v[: train_end + 1]) < 10
            else "medium"
            if np.mean(v[: train_end + 1]) < 50
            else "large"
        )
        for name, v in series.items()
    }
    seg_thresholds = {}
    seg_predictions = np.zeros(len(vy), dtype=bool)
    for group in sorted(set(groups.values())):
        idx = np.asarray([groups[n] == group for n in vnames])
        st, sm = choose_threshold(np.asarray(vy)[idx], np.asarray(vp)[idx])
        seg_thresholds[group] = st
        seg_predictions[idx] = np.asarray(vp)[idx] >= st
    seg_metric = classification(vy, seg_predictions)
    trials.append(
        {
            "name": "segmented_thresholds",
            "thresholds": seg_thresholds,
            "validation": seg_metric,
        }
    )
    use_segments = (
        seg_metric["precision_percent"] >= 40
        and seg_metric["alert_rate_percent"] <= 25
        and seg_metric["f2"] > winner["validation"]["f2"]
    )
    # Numeric candidates keep the same features/target and use validation MAE.
    rx, ry = samples(series, dates, train_end)
    regressors = {
        "v1_poisson": old_model,
        "absolute_error": HistGradientBoostingRegressor(
            loss="absolute_error",
            max_iter=150,
            max_leaf_nodes=7,
            min_samples_leaf=40,
            l2_regularization=5,
            early_stopping=False,
            random_state=42,
        ),
        "poisson_regularized": HistGradientBoostingRegressor(
            loss="poisson",
            max_iter=150,
            max_leaf_nodes=7,
            min_samples_leaf=60,
            l2_regularization=10,
            early_stopping=False,
            random_state=42,
        ),
    }
    numeric = []
    validations = {}
    for name, reg in regressors.items():
        if name != "v1_poisson":
            reg.fit(rx, ry)
        va, by = assess(reg, series, dates, [train_end, train_end + 7])
        validations[name] = (va, by)
        numeric.append({"name": name, "validation": va})
        print("numeric", name, va["ml"], flush=True)
    reg_name = min(numeric, key=lambda t: t["validation"]["ml"]["mae"])["name"]
    model = MonitoringModel(regressors[reg_name], detector, threshold)
    model.segment_thresholds = seg_thresholds if use_segments else {}
    model.groups = groups
    # Selection locked before any reused-test scoring.
    selection = {
        "risk_model": winner["name"],
        "threshold": threshold,
        "segment_thresholds": model.segment_thresholds,
        "regressor": reg_name,
    }
    (root / "selection-v2.json").write_text(json.dumps(selection, indent=2))
    test, test_by = assess(model, series, dates, [valid_end, valid_end + 7])
    _, _, ty, tp, tnames, tfolds = evaluated(
        detector, series, dates, [valid_end, valid_end + 7], threshold
    )

    def decisions(names, probabilities):
        return [
            score >= model.segment_thresholds.get(groups[name], threshold)
            for name, score in zip(names, probabilities, strict=False)
        ]

    alert_test = classification(ty, decisions(tnames, tp))
    for fold in tfolds:
        fold["metrics"] = classification(
            fold.pop("actual"), decisions(list(series), fold.pop("scores"))
        )
    for fold in vfolds:
        fold["metrics"] = classification(
            fold.pop("actual"), decisions(list(series), fold.pop("scores"))
        )
    segment_report = {}
    for group in sorted(set(groups.values())):
        indices = [i for i, n in enumerate(tnames) if groups[n] == group]
        segment_report[group] = classification(
            np.asarray(ty)[indices], np.asarray(decisions(tnames, tp))[indices]
        )
    # Additional earlier rolling-origin check, disjoint targets, architecture unchanged.
    early_end = train_end - 14
    early_series = {
        n: v
        for n, v in series.items()
        if sum(v[: early_end + 1]) >= 100 and sum(a > 0 for a in v[: early_end + 1]) >= 28
    }
    ex, ey = risk_samples(early_series, dates, early_end)
    early_detector = copy.deepcopy(detector)
    for est in early_detector if isinstance(early_detector, list) else [early_detector]:
        est.fit(ex, ey)
    _, early_metrics, *_ = evaluated(
        early_detector, early_series, dates, [early_end, early_end + 7], threshold
    )
    va, v_by = validations[reg_name]
    qualities = {}
    for name, vr in v_by.items():
        baseline = vr["naive"] if report["baseline"] == "weekly_naive" else vr["mean"]
        qualities[name] = {
            "validation_ml": metrics(vr["actual"], vr["ml"]),
            "validation_baseline": metrics(vr["actual"], baseline),
            "baseline": report["baseline"],
            "weekly_error_max": round(max(vr["weekly_errors"]), 1),
            "status": "SUPPORTED"
            if metrics(vr["actual"], vr["ml"])["mae"]
            < metrics(vr["actual"], baseline)["mae"]
            else "EXPERIMENTAL",
        }
    codehash = hashlib.sha256(
        Path(__file__).read_bytes()
        + Path("ml/risk.py").read_bytes()
        + Path("ml/monitoring.py").read_bytes()
    ).hexdigest()
    model_id = "hospital-growth-v2-" + codehash[:10]
    previous_metrics = report["alert_test"].copy()
    a, b, c = (
        previous_metrics["true_positive"],
        previous_metrics["false_positive"],
        previous_metrics["false_negative"],
    )
    previous_metrics.update(
        f1=round(2 * a / (2 * a + b + c), 4), f2=round(5 * a / (5 * a + b + 4 * c), 4)
    )
    new_report = {
        **report,
        "model_id": model_id,
        "schema": "hospital-growth-v2",
        "model": f'{reg_name} + {winner["name"]}',
        "trained_at": datetime.now(UTC).isoformat(),
        "training_code_sha256": codehash,
        "risk_features": RISK_FEATURES,
        "risk_training_examples": len(y),
        "risk_positive_examples": int(y.sum()),
        "selection": selection,
        "experiments": trials,
        "numeric_experiments": numeric,
        "test": test,
        "validation": va,
        "alert_test": {**alert_test, "production_ready": False},
        "alert_validation": classification(vy, decisions(vnames, vp)),
        "alert_folds": tfolds,
        "validation_alert_folds": vfolds,
        "segment_metrics": segment_report,
        "earlier_check": {
            "train_end": dates[early_end],
            "hospitals": len(early_series),
            "metrics": early_metrics,
            "note": (
                "Selected architecture and global threshold applied earlier; "
                "diagnostic, not independent selection evidence."
            ),
        },
        "previous": {
            "model_id": report["model_id"],
            "alert_test": previous_metrics,
            "test": report["test"],
        },
        "test_status": "REUSED_TEST",
        "ml_better_on_test": test["ml"]["mae"] < test[report["baseline"]]["mae"],
        "limitations": report["limitations"]
        + [
            (
                "Последние две недели уже использовались ранее: это повторная "
                "оценка, не новый независимый тест."
            ),
            (
                "Оценка риска не является откалиброванной вероятностью; "
                "порог выбран по F2 на валидации."
            ),
        ],
    }
    audit_path = root / "source-audit.json"
    if audit_path.exists():
        new_report["source_audit"] = json.loads(audit_path.read_text())
    snapshots = []
    for origin in range(valid_end, len(dates)):
        forecast = predict(model, series, dates, origin)
        risks = model.risk_scores(series, dates, origin)
        alerts = []
        for name, values in series.items():
            cutoff = model.segment_thresholds.get(groups[name], threshold)
            a = alert_for(
                name,
                values,
                dates,
                origin,
                forecast[name],
                qualities[name],
                model_id,
                risk={"score": risks[name], "threshold": cutoff},
            )
            if a:
                alerts.append(a)
        alerts.sort(key=lambda a: (-a["risk_score"], -a["predicted_total"]))
        snapshots.append({**bundle["snapshots"][origin - valid_end], "alerts": alerts})
    artifact = {**joblib.load(old / "model.joblib"), "model": model, "model_id": model_id}
    joblib.dump(artifact, root / "model.joblib")
    new_report["artifact_sha256"] = hashlib.sha256(
        (root / "model.joblib").read_bytes()
    ).hexdigest()
    new_bundle = {
        "report": new_report,
        "snapshots": snapshots,
        "runtime": {**runtime, "qualities": qualities},
    }
    (root / "report.json").write_text(
        json.dumps(new_report, ensure_ascii=False, indent=2)
    )
    tmp = root / "bundle.tmp"
    tmp.write_text(json.dumps(new_bundle, ensure_ascii=False, allow_nan=False))
    tmp.replace(root / "bundle.json")
    print("SELECTED", selection, "TEST", alert_test, flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=2):
        main()
