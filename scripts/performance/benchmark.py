from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

ENDPOINTS = (
    "/api/v1/analytics/overview",
    "/api/v1/analytics/referrals/timeseries",
    "/api/v1/analytics/refusals/timeseries",
    "/api/v1/analytics/organizations",
)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[rank], 3)


def summarize(
    endpoint: str,
    latencies_ms: list[float],
    errors: int,
    concurrency: int,
    cache_state: str,
    dataset_size: dict[str, int],
    status_counts: dict[str, int] | None = None,
    total_requests: int | None = None,
    path_mode: str = "edge",
) -> dict[str, Any]:
    requests = total_requests if total_requests is not None else len(latencies_ms)
    statuses = status_counts or {}
    failures = {
        "nginx_throttling": statuses.get("429", 0),
        "dependency_unavailable": statuses.get("503", 0),
        "client_timeout": statuses.get("CLIENT_TIMEOUT", 0),
        "network_error": statuses.get("NETWORK_ERROR", 0),
        "http_5xx": sum(
            count
            for status, count in statuses.items()
            if status.isdigit() and 500 <= int(status) < 600 and status != "503"
        ),
    }
    return {
        "endpoint": endpoint,
        "path_mode": path_mode,
        "concurrency": concurrency,
        "requests": requests,
        "successful_latency_samples": len(latencies_ms),
        "errors": errors,
        "error_rate": round(errors / requests, 6) if requests else 0.0,
        "status_counts": statuses,
        "failure_classes": {name: count for name, count in failures.items() if count},
        "cache_state": cache_state,
        "dataset_size": dataset_size,
        "p50_ms": _percentile(latencies_ms, 0.50),
        "p95_ms": _percentile(latencies_ms, 0.95),
        "p99_ms": _percentile(latencies_ms, 0.99),
    }


async def _token(client: httpx.AsyncClient, base: str) -> str:
    username = os.environ["PHASE8_TEST_USERNAME"]
    password = os.environ["PHASE8_TEST_PASSWORD"]
    response = await client.post(
        f"{base}/auth/realms/medsignal/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "medsignal-frontend",
            "username": username,
            "password": password,
        },
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


async def _measure(
    client: httpx.AsyncClient,
    base: str,
    endpoint: str,
    token: str,
    requests: int,
    concurrency: int,
) -> tuple[list[float], dict[str, int]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one() -> tuple[float, str]:
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await client.get(
                    f"{base}{endpoint}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                status = str(response.status_code)
            except httpx.TimeoutException:
                status = "CLIENT_TIMEOUT"
            except httpx.HTTPError:
                status = "NETWORK_ERROR"
            return (time.perf_counter() - started) * 1000, status

    outcomes = await asyncio.gather(*(one() for _ in range(requests)))
    return (
        [latency for latency, status in outcomes if status == "200"],
        dict(Counter(status for _, status in outcomes)),
    )


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    limits = httpx.Limits(max_connections=args.concurrency)
    async with httpx.AsyncClient(timeout=args.timeout, limits=limits) as client:
        token = os.getenv(args.token_env) or await _token(
            client, args.token_base_url or args.base_url
        )
        results = []
        for endpoint in args.endpoint:
            latencies, statuses = await _measure(
                client,
                args.base_url,
                endpoint,
                token,
                args.requests,
                args.concurrency,
            )
            results.append(
                summarize(
                    endpoint,
                    latencies,
                    sum(count for status, count in statuses.items() if status != "200"),
                    args.concurrency,
                    args.cache_state,
                    args.dataset_size,
                    statuses,
                    total_requests=args.requests,
                    path_mode=args.path_mode,
                )
            )
        return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost")
    parser.add_argument(
        "--token-base-url",
        help="Optional public OIDC gateway when API traffic targets a private backend.",
    )
    parser.add_argument("--endpoint", action="append", choices=ENDPOINTS)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--cache-state", choices=("cold", "warm"), required=True)
    parser.add_argument("--path-mode", choices=("edge", "backend"), default="edge")
    parser.add_argument("--token-env", default="PERFORMANCE_BEARER_TOKEN")
    parser.add_argument("--max-error-rate", type=float)
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument("--dataset-size", type=json.loads, default={})
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.endpoint = args.endpoint or list(ENDPOINTS)
    if not 1 <= args.concurrency <= 100 or not 1 <= args.requests <= 10000:
        parser.error("concurrency/requests outside bounded acceptance range")
    if args.max_error_rate is not None and not 0 <= args.max_error_rate <= 1:
        parser.error("max-error-rate must be between 0 and 1")
    if args.max_p95_ms is not None and args.max_p95_ms <= 0:
        parser.error("max-p95-ms must be positive")
    if not isinstance(args.dataset_size, dict) or any(
        name not in {"referrals", "waiting", "refusals", "treated"}
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        for name, size in args.dataset_size.items()
    ):
        parser.error("dataset-size must contain nonnegative core dataset counts")
    results = asyncio.run(run(args))
    report = {"results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if args.max_error_rate is not None and any(
        item["error_rate"] > args.max_error_rate for item in results
    ):
        return 1
    if args.max_p95_ms is not None and any(
        item["p95_ms"] is None or item["p95_ms"] > args.max_p95_ms for item in results
    ):
        return 1
    return 1 if any(item["errors"] for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
