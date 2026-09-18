from __future__ import annotations

from scripts.performance.background_jobs import build_measurement, build_report


def test_background_measurement_contains_reproducibility_context() -> None:
    measurement = build_measurement(
        job="signals.evaluate",
        status="COMPLETED",
        duration_seconds=12.34567,
        measurement_source="wall_clock",
        dataset_size={"referrals": 767130, "refusals": 1508732},
    )

    assert measurement == {
        "job": "signals.evaluate",
        "status": "COMPLETED",
        "duration_seconds": 12.346,
        "measurement_source": "wall_clock",
        "dataset_size": {"referrals": 767130, "refusals": 1508732},
    }


def test_background_report_keeps_each_job_separate() -> None:
    measurements = [
        build_measurement("data.import", "COMPLETED", 1.0, "persistent_timestamps", {}),
        build_measurement("signals.evaluate", "COMPLETED", 2.0, "wall_clock", {}),
        build_measurement(
            "ml.train_referral_forecast", "COMPLETED", 3.0, "wall_clock", {}
        ),
    ]

    report = build_report(measurements, generated_at="2026-09-18T00:00:00Z")

    assert report["generated_at"] == "2026-09-18T00:00:00Z"
    assert [item["job"] for item in report["measurements"]] == [
        "data.import",
        "signals.evaluate",
        "ml.train_referral_forecast",
    ]
