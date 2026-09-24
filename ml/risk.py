"""Past-only learned growth detection; score is not a calibrated probability."""

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RISK_FEATURES = [
    "week1",
    "week2",
    "week3",
    "week4",
    "trend12",
    "trend23",
    "trend14",
    "recent3_ratio",
    "last_ratio",
    "cv28",
    "zero28",
    "max_ratio",
    "min_ratio",
    "slope",
    "weekday",
    "log_volume",
    "active28",
    "weekend_share",
]


def risk_features(values, dates, origin):
    from datetime import date

    h = np.asarray(values[origin - 27 : origin + 1], dtype=float)
    if len(h) != 28:
        raise ValueError("28 days required")
    weeks = [
        float(h[-7 * (i + 1) : len(h) - 7 * i if i else None].sum()) for i in range(4)
    ]
    avg = h.mean()
    scale = max(avg, 1)
    return [
        *weeks,
        weeks[0] / max(weeks[1], 1),
        weeks[1] / max(weeks[2], 1),
        weeks[0] / max(weeks[3], 1),
        float(h[-3:].mean() / scale),
        h[-1] / scale,
        float(h.std() / scale),
        float((h == 0).mean()),
        float(h.max() / scale),
        float(h.min() / scale),
        float(np.polyfit(np.arange(28), h, 1)[0] / scale),
        date.fromisoformat(dates[origin]).weekday(),
        float(np.log1p(avg)),
        int((h > 0).sum()),
        float(
            sum(
                h[i]
                for i in range(28)
                if date.fromisoformat(dates[origin - 27 + i]).weekday() >= 5
            )
            / max(h.sum(), 1)
        ),
    ]


def growth_label(values, origin):
    ref = sum(values[origin - 27 : origin + 1]) / 4
    total = sum(values[origin + 1 : origin + 8])
    return int(ref >= 20 and total - ref >= 10 and total >= ref * 1.2)


def risk_samples(series, dates, cutoff):
    x, y = [], []
    for values in series.values():
        for origin in range(27, cutoff - 6):
            x.append(risk_features(values, dates, origin))
            y.append(growth_label(values, origin))
    return np.asarray(x), np.asarray(y)


def candidates():
    result = {}
    for balanced in (False, True):
        weight = "balanced" if balanced else None
        result[f"logistic_{balanced}"] = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=0.3, max_iter=1000, class_weight=weight, random_state=42
            ),
        )
        for leaves in (7, 15):
            result[f"hgb_{leaves}_{balanced}"] = HistGradientBoostingClassifier(
                max_iter=120,
                max_leaf_nodes=leaves,
                learning_rate=0.05,
                min_samples_leaf=40,
                l2_regularization=5,
                early_stopping=False,
                class_weight=weight,
                random_state=42,
            )
    result["extra_trees"] = ExtraTreesClassifier(
        n_estimators=180,
        max_depth=10,
        min_samples_leaf=20,
        class_weight="balanced",
        n_jobs=2,
        random_state=42,
    )
    return result


def scores(estimator, series, dates, origin):
    names = list(series)
    x = np.asarray([risk_features(series[n], dates, origin) for n in names])
    if isinstance(estimator, list):
        p = np.mean([m.predict_proba(x)[:, 1] for m in estimator], axis=0)
    else:
        p = estimator.predict_proba(x)[:, 1]
    return {
        n: float(p[i]) if sum(series[n][origin - 27 : origin + 1]) / 4 >= 20 else 0.0
        for i, n in enumerate(names)
    }


def classification(y, p):
    y = np.asarray(y, dtype=bool)
    p = np.asarray(p, dtype=bool)
    tp = int((y & p).sum())
    fp = int((~y & p).sum())
    fn = int((y & ~p).sum())
    tn = int((~y & ~p).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision_percent": round(precision * 100, 2),
        "recall_percent": round(recall * 100, 2),
        "f1": round(2 * precision * recall / (precision + recall), 4)
        if precision + recall
        else 0.0,
        "f2": round(5 * precision * recall / (4 * precision + recall), 4)
        if precision + recall
        else 0.0,
        "alert_count": tp + fp,
        "alert_rate_percent": round(100 * (tp + fp) / len(y), 2),
        "cases": len(y),
    }


def choose_threshold(y, p):
    options = [
        (float(t), classification(y, np.asarray(p) >= t))
        for t in np.arange(0.05, 0.901, 0.025)
    ]
    allowed = [
        a
        for a in options
        if a[1]["precision_percent"] >= 40 and a[1]["alert_rate_percent"] <= 25
    ]
    if not allowed:
        allowed = [a for a in options if a[1]["alert_rate_percent"] <= 25]
    return max(
        allowed,
        key=lambda a: (
            a[1]["f2"],
            a[1]["precision_percent"],
            -a[1]["alert_rate_percent"],
        ),
    )


class MonitoringModel:
    def __init__(self, regressor, detector, threshold):
        self.regressor = regressor
        self.detector = detector
        self.threshold = threshold

    def predict(self, x):
        return self.regressor.predict(x)

    def risk_scores(self, series, dates, origin):
        return scores(self.detector, series, dates, origin)


def risk_context(model, name, predictions):
    if predictions is None:
        return None
    group = model.groups[name]
    return {
        "score": predictions[name],
        "threshold": model.segment_thresholds.get(group, model.threshold),
    }
