"""Hand-counted episodes guard against daily alert inflation and fake certainty."""

from datetime import date, timedelta

import pytest


def api():
    from ml.evaluation import monitoring as evaluation

    return evaluation


def episodes():
    e = api()
    start = date(2026, 7, 1)
    # 4 TP, 1 FP, 1 FN, 2 TN across two organizations and four blocks.
    pairs = [(True, True)] * 4 + [
        (False, True),
        (True, False),
        (False, False),
        (False, False),
    ]
    return [
        e.AlertEpisode(
            "A" if i < 4 else "B",
            start + timedelta(days=(i % 4) * 7),
            actual,
            predicted,
            start + timedelta(days=(i % 4) * 7 - 2) if predicted else None,
        )
        for i, (actual, predicted) in enumerate(pairs)
    ]


def test_precision_and_recall_count_misses_and_false_alarms():
    e = api()
    assert hasattr(e, "AlertCounts"), "episode metrics not implemented"
    counts = e.AlertCounts(6, 8, 142, 0)
    assert e.precision(counts) == 6 / 14
    assert e.recall(counts) == 6 / 148
    assert e.precision(e.AlertCounts(0, 0, 1, 1)) is None
    assert e.recall(e.AlertCounts(0, 1, 0, 1)) is None
    assert e.forecast_metrics([0, 0], [1, 2])["wape"] is None
    assert e.forecast_metrics([], []) == {"mae": None, "wape": None, "points": 0}


def test_weekly_episodes_have_explicit_workload_and_lead_time():
    result = api().episode_metrics(episodes())
    assert result["counts"] == {"tp": 4, "fp": 1, "fn": 1, "tn": 2}
    assert result["precision"] == 0.8
    assert result["recall"] == 0.8
    assert result["alerts_per_org_week"] == 5 / 8
    assert result["false_alerts_per_org_week"] == 1 / 8
    assert result["sample_support"] == {
        "organizations": 2,
        "evaluation_windows": 4,
        "org_weeks": 8,
        "positive_episodes": 5,
    }
    assert result["lead_time_days"] == 2


def test_duplicate_and_overlapping_episodes_cannot_inflate_support():
    from dataclasses import replace

    values = episodes()
    with pytest.raises(ValueError):
        api().episode_metrics([*values, values[0]])
    with pytest.raises(ValueError):
        api().episode_metrics(
            [*values, replace(values[0], window_start=date(2026, 7, 2))]
        )
    with pytest.raises(ValueError):
        api().episode_metrics([replace(values[0], issued_on=date(2026, 7, 2))])


def test_unknown_outcomes_are_excluded_and_not_true_negatives():
    from dataclasses import replace

    values = [replace(episodes()[0], actual_positive=None)]
    result = api().episode_metrics(values)
    assert result["counts"] == {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    assert result["excluded_episodes"] == 1
    assert result["precision"] is None
    assert result["alerts_per_org_week"] is None


def test_daily_alert_clusters_are_separate_from_weekly_episode_counts():
    records = [("A", date(2026, 7, d)) for d in (1, 2, 3, 8)] + [("B", date(2026, 7, 2))]
    result = api().daily_alert_clusters(records)
    assert result["alert_days"] == 5
    assert result["clusters"] == 3
    assert result["by_organization"] == {"A": 2, "B": 1}


def test_uncertainty_resamples_both_organization_and_time_clusters():
    result = api().cluster_uncertainty(episodes(), seed=42, resamples=200)
    assert result == api().cluster_uncertainty(episodes(), seed=42, resamples=200)
    assert result["method"] == "crossed-organization-week-bootstrap"
    assert result["organization_clusters"] == 2
    assert result["time_blocks"] == 4
    assert result["intervals"]["precision"][0] < 0.8 < result["intervals"]["precision"][1]
    assert result["valid_resamples"]["precision"] <= 200
    short = api().cluster_uncertainty(episodes()[:2], seed=42, resamples=200)
    assert short["intervals"] is None
    assert short["reason"] == "TOO_FEW_INDEPENDENT_CLUSTERS"


def test_growth_label_uses_only_prior_complete_reference_days():
    e = api()
    assert e.growth_label([10] * 28, [12] * 7)
    assert not e.growth_label([10] * 28, [10] * 7)
    assert e.growth_label([None] + [10] * 27, [100] * 7) is None
    with pytest.raises(ValueError):
        e.growth_label([10] * 27, [100] * 7)
