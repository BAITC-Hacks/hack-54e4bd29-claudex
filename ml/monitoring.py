"""Legacy Q1 pilot reproduction (legacy-q1-v1), not independent admission evidence.

Only registration date and receiving organisation enter the model. Outcomes,
patient identifiers and diagnosis fields are deliberately not used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import joblib
import numpy as np
from numpy.typing import ArrayLike
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

if TYPE_CHECKING:
    from ml.monitoring_contracts import AggregateManifest, SplitSpec

LEGACY_PATH_VERSION = "legacy-q1-v1"

SCHEMA = "hospital-referrals-direct7-v1"
FEATURES = [
    "lag1",
    "lag2",
    "lag3",
    "lag7",
    "lag14",
    "mean7",
    "mean14",
    "mean28",
    "std7",
    "same_weekday_last_week",
    "target_weekday",
    "horizon",
]
SOURCE_URL = "https://ashyq.data.gov.kz/dataset/magda-ds-4b553445-0570-4302-87e7-48e1edacfa41/details"


def aggregate(
    paths: list[Path],
) -> tuple[list[str], dict[str, list[int]], dict[str, Any]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    source_dates: Counter[str] = Counter()
    audit: dict[str, Any] = {
        "rows": 0,
        "accepted": 0,
        "invalid": 0,
        "files": [],
        "source_url": SOURCE_URL,
    }
    hashes = set()
    for path in sorted(paths):
        digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
        if digest in hashes:
            raise ValueError(
                "Duplicate source file; refusing double-counted training data"
            )
        hashes.add(digest)
        n = 0
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not {"hospital_mo", "registration_dt"} <= set(reader.fieldnames or []):
                raise ValueError(f"{path.name}: missing required referral columns")
            for row in reader:
                n += 1
                name = (row.get("hospital_mo") or "").strip()
                try:
                    day = date.fromisoformat(
                        (row.get("registration_dt") or "")[:10]
                    ).isoformat()
                    if not name:
                        raise ValueError("Missing organisation")
                except ValueError:
                    audit["invalid"] += 1
                    continue
                counts[name][day] += 1
                source_dates[day] += 1
                audit["accepted"] += 1
        audit["rows"] += n
        audit["files"].append({"name": path.name, "sha256": digest, "rows": n})
    if not source_dates:
        raise ValueError("No valid referrals")
    start, end = (
        date.fromisoformat(min(source_dates)),
        date.fromisoformat(max(source_dates)),
    )
    dates = [
        (start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
    ]
    if any(day not in source_dates for day in dates):
        raise ValueError(
            "Entire source days are missing; do not impute an incomplete export as zero"
        )
    audit["zero_policy"] = (
        "No row for an organisation on a source-covered day means zero recorded "
        "referrals; not proof of complete reporting."
    )
    # Organisation names remain source identifiers; no unverified regional mapping.
    series = {
        name: [values.get(day, 0) for day in dates] for name, values in counts.items()
    }
    return dates, series, audit


def features(
    values: list[int], dates: list[str], origin: int, horizon: int
) -> list[float]:
    """origin is last observed day; features never access a later observation."""
    if origin < 27 or not 1 <= horizon <= 7:
        raise ValueError("Need 28 observed days and horizon 1..7")
    hist = values[origin - 27 : origin + 1]
    target = date.fromisoformat(dates[origin]) + timedelta(days=horizon)
    return [
        hist[-1],
        hist[-2],
        hist[-3],
        hist[-7],
        hist[-14],
        float(np.mean(hist[-7:])),
        float(np.mean(hist[-14:])),
        float(np.mean(hist)),
        float(np.std(hist[-7:])),
        values[origin + horizon - 7],
        target.weekday(),
        horizon,
    ]


def samples(
    series: dict[str, list[int]], dates: list[str], cutoff: int
) -> tuple[np.ndarray, np.ndarray]:
    x, y = [], []
    for values in series.values():
        for origin in range(27, cutoff):
            for horizon in range(1, min(7, cutoff - origin) + 1):
                x.append(features(values, dates, origin, horizon))
                y.append(values[origin + horizon])
    return np.asarray(x), np.asarray(y)


def metrics(actual: ArrayLike, predicted: ArrayLike) -> dict[str, Any]:
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    error = np.abs(actual - predicted)
    return {
        "mae": round(float(error.mean()), 3),
        "wape": round(float(error.sum() / actual.sum() * 100), 3)
        if actual.sum()
        else None,
        "points": int(actual.size),
    }


def predict(
    model: HistGradientBoostingRegressor,
    series: dict[str, list[int]],
    dates: list[str],
    origin: int,
) -> dict[str, list[float]]:
    names = list(series)
    x = [features(series[name], dates, origin, h) for name in names for h in range(1, 8)]
    pred = np.maximum(0, model.predict(x)).reshape(len(names), 7)
    return {name: pred[i].tolist() for i, name in enumerate(names)}


def assess(
    model: HistGradientBoostingRegressor,
    series: dict[str, list[int]],
    dates: list[str],
    origins: list[int],
) -> tuple[dict[str, Any], dict[str, dict[str, list[float]]]]:
    actual, ml, naive, mean = [], [], [], []
    by_hospital: dict[str, dict[str, list[float]]] = {
        name: {"actual": [], "ml": [], "naive": [], "mean": [], "weekly_errors": []}
        for name in series
    }
    folds = []
    for origin in origins:
        predictions = predict(model, series, dates, origin)
        a, p, b, m = [], [], [], []
        for name, values in series.items():
            truth = values[origin + 1 : origin + 8]
            baseline = values[origin - 6 : origin + 1]
            average = [float(np.mean(values[origin - 6 : origin + 1]))] * 7
            forecast = predictions[name]
            a.extend(truth)
            p.extend(forecast)
            b.extend(baseline)
            m.extend(average)
            target = by_hospital[name]
            comparisons: list[tuple[str, Sequence[float]]] = [
                ("actual", truth),
                ("ml", forecast),
                ("naive", baseline),
                ("mean", average),
            ]
            for key, vals in comparisons:
                target[key].extend(vals)
            target["weekly_errors"].append(abs(sum(truth) - sum(forecast)))
        actual.extend(a)
        ml.extend(p)
        naive.extend(b)
        mean.extend(m)
        folds.append(
            {
                "as_of": dates[origin],
                "start": dates[origin + 1],
                "end": dates[origin + 7],
                "ml": metrics(a, p),
                "weekly_naive": metrics(a, b),
                "mean7": metrics(a, m),
            }
        )
    return {
        "ml": metrics(actual, ml),
        "weekly_naive": metrics(actual, naive),
        "mean7": metrics(actual, mean),
        "folds": folds,
    }, by_hospital


def alert_for(
    name: str,
    values: list[int],
    dates: list[str],
    origin: int,
    prediction: list[float],
    quality: dict[str, Any],
    model_id: str,
    *,
    risk: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    reference = sum(values[origin - 27 : origin + 1]) / 4
    total = sum(prediction)
    delta = total - reference
    growth = delta / reference * 100 if reference else 0
    if reference < 20 or delta < 10 or growth < 20:
        return None
    severity = "CRITICAL" if growth >= 50 else "HIGH" if growth >= 35 else "WARNING"
    signal_id = hashlib.sha256(f"{model_id}|{name}|{dates[origin]}".encode()).hexdigest()[
        :20
    ]
    alert: dict[str, Any] = {
        "id": signal_id,
        "hospital": name,
        "as_of": dates[origin],
        "severity": severity,
        "title": f"Ожидается рост направлений на {growth:.0f}%",
        "description": (
            f"На следующие 7 дней модель ожидает {total:.0f} направлений. "
            f"Обычный недельный поток за последние 28 дней — {reference:.0f}."
        ),
        "why_dangerous": (
            "При неизменной пропускной способности рост входящего потока может "
            "увеличить ожидание. Данных о свободных койках нет: перегрузка и рост "
            "очереди пока не подтверждены."
        ),
        "predicted_total": round(total, 1),
        "reference_total": round(reference, 1),
        "extra_referrals": round(delta, 1),
        "growth_percent": round(growth, 1),
        "model_id": model_id,
        "quality": quality,
        "forecast": [
            {
                "date": (
                    date.fromisoformat(dates[origin]) + timedelta(days=h)
                ).isoformat(),
                "value": round(value, 1),
            }
            for h, value in enumerate(prediction, 1)
        ],
        "actions": [
            {
                "owner": "Координатор госпитализации",
                "when": "Сегодня",
                "text": (
                    "Проверить план приёма на следующие 7 дней: ожидается примерно "
                    f"{total:.0f} направлений, на {delta:.0f} больше обычного."
                ),
                "check": (
                    "Сопоставить прогноз с доступными местами по профилям; записать "
                    "подтверждённый дефицит или отсутствие дефицита."
                ),
            },
            {
                "owner": "Руководитель принимающей организации",
                "when": "После проверки вместимости",
                "text": (
                    "Если дефицит подтверждён, согласовать дополнительные плановые места "
                    "или возможность направления в другую организацию по нужному профилю."
                ),
                "check": (
                    "Указать согласованное число мест и ответственного. "
                    "Автоматический перевод пациентов не выполняется."
                ),
            },
            {
                "owner": "Аналитик",
                "when": "На следующий день",
                "text": (
                    "Сверить фактическое число новых направлений с прогнозом и "
                    "проверить полноту выгрузки."
                ),
                "check": "Повторить расчёт после поступления нового дня данных.",
            },
        ],
        "action_basis": (
            "Правила реагирования, а не обученная модель выбора лечения или "
            "доказанный эффект вмешательства."
        ),
        "effect": (
            "Эффект на очередь не рассчитан: нужны вместимость, текущая очередь и "
            "история управленческих действий."
        ),
        "trigger": (
            "Прогноз обученной модели ≥120% средней недели за 28 дней, прирост ≥10 "
            "направлений, обычный поток ≥20. Пороги пилотные, не медицинские нормативы."
        ),
    }
    if risk is not None:
        # Research ranking score only; never a calibrated overload probability.
        alert["risk_score"] = risk["score"]
        alert["risk_threshold"] = risk["threshold"]
    return alert


def prepare_approved_experiment(
    rows: list[dict[str, object]], manifest: AggregateManifest, split: SplitSpec
) -> dict[str, Any]:
    """New v2 path accepts only a trusted approved aggregate manifest and rows.

    No raw-source discovery or fitting occurs here. Owner approval and independent
    evidence remain separate admission gates.
    """
    from ml.evaluation.monitoring import eligible_organizations, load_approved_aggregates

    series = load_approved_aggregates(rows, manifest)
    return {
        "path_version": "approved-aggregate-v2",
        "series": series,
        "eligible_organizations": eligible_organizations(series, split),
        "manifest_sha256": manifest.sha256,
        "dataset_sha256": manifest.aggregate_sha256,
    }


def train(source: Path, output: Path) -> None:
    """Preserved legacy-q1-v1 reproduction only; never an admission experiment."""
    paths = sorted(source.glob("referrals_part_*.csv"))
    if len(paths) != 3:
        raise ValueError(
            "Expected all three referrals_part_*.csv exports; "
            "incomplete source is not accepted"
        )
    dates, all_series, audit = aggregate(paths)
    n = len(dates)
    if n < 84:
        raise ValueError("At least 84 complete calendar days required")
    train_end, validation_end = n - 29, n - 15
    # Eligibility uses training history only, never the held-out future.
    series = {
        name: vals
        for name, vals in all_series.items()
        if sum(vals[: train_end + 1]) >= 100
        and sum(v > 0 for v in vals[: train_end + 1]) >= 28
    }
    if not series:
        raise ValueError("No organisations with sufficient training history")
    x, y = samples(series, dates, train_end)
    model = HistGradientBoostingRegressor(
        loss="poisson",
        learning_rate=0.05,
        max_iter=180,
        max_leaf_nodes=15,
        min_samples_leaf=30,
        l2_regularization=1,
        early_stopping=False,
        random_state=42,
    )
    model.fit(x, y)
    validation, v_by = assess(model, series, dates, [train_end, train_end + 7])
    baseline = min(("weekly_naive", "mean7"), key=lambda k: validation[k]["mae"])
    # Frozen model and baseline choice are scored on the final 14 unseen days.
    test, t_by = assess(model, series, dates, [validation_end, validation_end + 7])
    stamp = datetime.now(UTC).isoformat()
    fingerprint = hashlib.sha256(
        json.dumps(audit["files"], sort_keys=True).encode()
    ).hexdigest()
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    model_id = f"{SCHEMA}-{fingerprint[:8]}-{code_hash[:8]}"
    report = {
        "model_id": model_id,
        "schema": SCHEMA,
        "model": "HistGradientBoostingRegressor (Poisson)",
        "trained_at": stamp,
        "features": FEATURES,
        "source": audit,
        "period_start": dates[0],
        "period_end": dates[-1],
        "days": n,
        "train_end": dates[train_end],
        "validation_start": dates[train_end + 1],
        "validation_end": dates[validation_end],
        "test_start": dates[validation_end + 1],
        "test_end": dates[-1],
        "training_examples": len(y),
        "hospitals": len(series),
        "excluded_hospitals": len(all_series) - len(series),
        "validation": validation,
        "test": test,
        "baseline": baseline,
        "dataset_sha256": fingerprint,
        "training_code_sha256": code_hash,
        "ml_better_on_test": test["ml"]["mae"] < test[baseline]["mae"],
        "limitations": [
            "90 дней истории не подтверждают годовую сезонность.",
            "Число записей о направлениях не равно числу уникальных пациентов.",
            "Нет истории ежедневных очередей, вместимости и результатов вмешательств.",
            "Нули означают отсутствие записей, "
            "полнота отчётности отдельно не подтверждена.",
            "Результаты проверки прогноза не подтверждают "
            "точность предупреждений о перегрузке.",
        ],
    }
    snapshots: list[dict[str, Any]] = []
    qualities = {}
    for origin in range(validation_end, n):
        forecasts = predict(model, series, dates, origin)
        alerts = []
        for name, values in series.items():
            vr = v_by[name]
            bm = vr["naive"] if baseline == "weekly_naive" else vr["mean"]
            quality = {
                "validation_ml": metrics(vr["actual"], vr["ml"]),
                "validation_baseline": metrics(vr["actual"], bm),
                "baseline": baseline,
                "weekly_error_max": round(max(vr["weekly_errors"]), 1),
                "status": "SUPPORTED"
                if metrics(vr["actual"], vr["ml"])["mae"]
                < metrics(vr["actual"], bm)["mae"]
                else "EXPERIMENTAL",
            }
            qualities[name] = quality
            alert = alert_for(
                name, values, dates, origin, forecasts[name], quality, model_id
            )
            if alert:
                alerts.append(alert)
        alerts.sort(
            key=lambda a: (
                -{"CRITICAL": 3, "HIGH": 2, "WARNING": 1}[a["severity"]],
                -a["extra_referrals"],
            )
        )
        snapshots.append(
            {
                "as_of": dates[origin],
                "new_records": sum(v[origin] for v in all_series.values()),
                "hospitals_checked": len(series),
                "alerts": alerts,
            }
        )
    # Separate forecast accuracy from warning detection;
    # count both false alarms and misses.
    tp = fp = fn = tn = 0
    for index in (0, 7):
        origin = validation_end + index
        signalled = {a["hospital"] for a in snapshots[index]["alerts"]}
        for name, values in series.items():
            reference = sum(values[origin - 27 : origin + 1]) / 4
            actual_total = sum(values[origin + 1 : origin + 8])
            actual_growth = (
                reference >= 20
                and actual_total - reference >= 10
                and actual_total >= reference * 1.2
            )
            predicted_growth = name in signalled
            tp += int(predicted_growth and actual_growth)
            fp += int(predicted_growth and not actual_growth)
            fn += int(not predicted_growth and actual_growth)
            tn += int(not predicted_growth and not actual_growth)
    report["alert_test"] = {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision_percent": round(100 * tp / (tp + fp), 2) if tp + fp else None,
        "recall_percent": round(100 * tp / (tp + fn), 2) if tp + fn else None,
        "label": "Recorded weekly referral growth, not hospital overload",
        "production_ready": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "train_end": dates[train_end],
            "model_id": model_id,
        },
        output / "model.joblib",
    )
    report["artifact_sha256"] = hashlib.file_digest(
        (output / "model.joblib").open("rb"), "sha256"
    ).hexdigest()
    bundle = {
        "report": report,
        "snapshots": snapshots,
        "runtime": {
            "dates": dates,
            "series": series,
            "qualities": qualities,
            "start_origin": validation_end,
            "daily_records": [sum(v[i] for v in all_series.values()) for i in range(n)],
        },
    }
    temp = output / "bundle.tmp"
    temp.write_text(
        json.dumps(bundle, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    temp.replace(output / "bundle.json")
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "rows": audit["rows"],
                "hospitals": len(series),
                "training_examples": len(y),
                "test": test,
                "alerts_by_day": [len(s["alerts"]) for s in snapshots],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/incoming"))
    parser.add_argument("--output", type=Path, default=Path("data/monitoring"))
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        train(args.source, args.output)
