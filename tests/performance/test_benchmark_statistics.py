from __future__ import annotations

from pathlib import Path

from scripts.performance.benchmark import summarize


def test_summary_contains_reproducibility_context() -> None:
    result = summarize(
        endpoint="/api/v1/analytics/overview",
        latencies_ms=[10.0, 20.0, 30.0, 40.0, 50.0],
        errors=1,
        concurrency=20,
        cache_state="warm",
        dataset_size={"referrals": 767130},
    )
    assert result["requests"] == 5
    assert result["concurrency"] == 20
    assert result["error_rate"] == 0.2
    assert result["cache_state"] == "warm"
    assert result["dataset_size"] == {"referrals": 767130}
    assert result["p50_ms"] == 30.0
    assert result["p95_ms"] >= result["p50_ms"]
    assert result["p99_ms"] >= result["p95_ms"]


def test_empty_measurement_is_explicit() -> None:
    result = summarize("/empty", [], 0, 1, "cold", {})
    assert result["requests"] == 0
    assert result["p50_ms"] is None


def test_benchmark_supports_separate_public_oidc_gateway() -> None:
    source = Path("scripts/performance/benchmark.py").read_text(encoding="utf-8")

    assert "args.token_base_url or args.base_url" in source
