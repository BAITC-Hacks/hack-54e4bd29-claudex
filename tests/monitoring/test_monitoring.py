import json
from datetime import date, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from ml.monitoring import aggregate, alert_for, features, metrics, samples
from pilot.api import create_app


def dates(n=90):
    return [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(n)]


def test_features_and_training_do_not_see_future():
    values = list(range(90))
    future = values[:62] + [100000] * 28
    for horizon in range(1, 8):
        assert features(values, dates(), 61, horizon) == features(
            future, dates(), 61, horizon
        )
    a, b = samples({"hospital": values}, dates(), 61)
    c, d = samples({"hospital": future}, dates(), 61)
    np.testing.assert_array_equal(a, c)
    np.testing.assert_array_equal(b, d)
    assert b.max() == 61


def test_training_changes_predictions_when_targets_change():
    x, y = samples({"hospital": [10 + (i % 7) * 5 for i in range(90)]}, dates(), 61)
    with threadpool_limits(limits=1):
        first = HistGradientBoostingRegressor(
            max_iter=30, early_stopping=False, random_state=42
        ).fit(x, y)
        second = HistGradientBoostingRegressor(
            max_iter=30, early_stopping=False, random_state=42
        ).fit(x, y + 50)
        assert np.mean(second.predict(x) - first.predict(x)) > 40


def test_alert_is_model_forecast_compared_with_history_not_baseline_disagreement():
    args = ("hospital", [10] * 90, dates(), 61)
    assert alert_for(*args, [10] * 7, {}, "model") is None
    alert = alert_for(*args, [20] * 7, {}, "model")
    assert alert["reference_total"] == 70
    assert alert["growth_percent"] == 100
    assert alert["severity"] == "CRITICAL"
    assert alert_for(*args, [20] * 7, {}, "model")["id"] == alert["id"]
    assert len(alert["actions"]) == 3


def test_missing_source_day_is_rejected(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text("hospital_mo,registration_dt\nA,2025-01-01\nA,2025-01-03\n")
    with pytest.raises(ValueError, match="missing"):
        aggregate([path])


def test_duplicate_export_is_rejected(tmp_path):
    p = tmp_path / "one.csv"
    q = tmp_path / "two.csv"
    p.write_text("hospital_mo,registration_dt\nA,2025-01-01\n")
    q.write_text(p.read_text())
    with pytest.raises(ValueError, match="Duplicate"):
        aggregate([p, q])


def test_zero_actual_wape_is_not_fake_zero_accuracy():
    assert metrics([0, 0], [1, 2])["wape"] is None


def bundle(tmp_path):
    value = {
        "report": {"model_id": "test"},
        "snapshots": [
            {"as_of": "2025-03-17", "alerts": [{"id": "a", "status": "NEW"}]},
            {"as_of": "2025-03-18", "alerts": [{"id": "b", "status": "NEW"}]},
        ],
    }
    (tmp_path / "bundle.json").write_text(json.dumps(value))


def test_replay_end_and_decisions_survive_restart(tmp_path):
    bundle(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        assert (
            client.post("/api/pilot/replay", json={"action": "step"}).status_code == 403
        )
        headers = {"X-MedSignal-Demo": "1"}
        assert client.get("/api/pilot/alerts/b").status_code == 404
        assert (
            client.patch(
                "/api/pilot/alerts/a", json={"status": "IN_PROGRESS"}, headers=headers
            ).status_code
            == 200
        )
        response = client.post(
            "/api/pilot/replay", json={"action": "step"}, headers=headers
        ).json()
        assert response["finished"] and response["index"] == 1
        assert (
            client.post(
                "/api/pilot/replay", json={"action": "step"}, headers=headers
            ).json()["index"]
            == 1
        )
        assert client.get("/api/pilot/alerts/a").json()["status"] == "IN_PROGRESS"
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/pilot/monitor").json()["index"] == 1
        assert client.get("/api/pilot/alerts/a").json()["status"] == "IN_PROGRESS"


def test_empty_install_never_returns_fabricated_results(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/pilot/monitor").status_code == 503
        assert client.get("/api/pilot/model").status_code == 503
        assert client.get("/api/pilot/alerts/missing").status_code == 503
        for headers in ({}, {"X-MedSignal-Demo": "invalid"}):
            for action in ("play", "pause", "step", "reset"):
                assert (
                    client.post(
                        "/api/pilot/replay", json={"action": action}, headers=headers
                    ).status_code
                    == 403
                )
            assert (
                client.patch(
                    "/api/pilot/alerts/missing",
                    json={"status": "CLOSED"},
                    headers=headers,
                ).status_code
                == 403
            )
        headers = {"X-MedSignal-Demo": "1"}
        assert (
            client.post(
                "/api/pilot/replay", json={"action": "step"}, headers=headers
            ).status_code
            == 503
        )
        assert (
            client.patch(
                "/api/pilot/alerts/missing", json={"status": "CLOSED"}, headers=headers
            ).status_code
            == 503
        )
    assert not (tmp_path / "replay-state.json").exists()
