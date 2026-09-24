from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx

from scripts.performance.benchmark import _measure, summarize


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


def test_latency_percentiles_exclude_429_503_and_client_timeout() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.statuses = iter([200, 429, 503, "timeout"])

        async def get(self, url: str, headers: dict[str, str]):  # noqa: ARG002
            outcome = next(self.statuses)
            if outcome == "timeout":
                raise httpx.ReadTimeout(
                    "synthetic timeout", request=httpx.Request("GET", url)
                )
            return SimpleNamespace(status_code=outcome)

    latencies, statuses = asyncio.run(
        _measure(
            FakeClient(), "http://localhost", "/api/v1/analytics/overview", "test", 4, 1
        )
    )
    result = summarize(
        "/api/v1/analytics/overview",
        latencies,
        errors=3,
        concurrency=1,
        cache_state="cold",
        dataset_size={"referrals": 100},
        status_counts=statuses,
        total_requests=4,
    )

    assert statuses == {"200": 1, "429": 1, "503": 1, "CLIENT_TIMEOUT": 1}
    assert len(latencies) == 1
    assert result["requests"] == 4
    assert result["successful_latency_samples"] == 1
    assert result["error_rate"] == 0.75
    assert result["failure_classes"] == {
        "nginx_throttling": 1,
        "dependency_unavailable": 1,
        "client_timeout": 1,
    }
