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
) -> dict[str, Any]:
    requests = len(latencies_ms)
    return {
        "endpoint": endpoint,
        "concurrency": concurrency,
        "requests": requests,
        "errors": errors,
        "error_rate": round(errors / requests, 6) if requests else 0.0,
        "status_counts": status_counts or {},
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
            except httpx.HTTPError:
                status = "NETWORK_ERROR"
            return (time.perf_counter() - started) * 1000, status

    outcomes = await asyncio.gather(*(one() for _ in range(requests)))
    return [item[0] for item in outcomes], dict(Counter(item[1] for item in outcomes))


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    limits = httpx.Limits(max_connections=args.concurrency)
    async with httpx.AsyncClient(timeout=args.timeout, limits=limits) as client:
        token = await _token(client, args.token_base_url or args.base_url)
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
    parser.add_argument("--endpoint", action="append", required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--cache-state", choices=("cold", "warm"), required=True)
    parser.add_argument("--dataset-size", type=json.loads, default={})
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 100 or not 1 <= args.requests <= 10000:
        parser.error("concurrency/requests outside bounded acceptance range")
    results = asyncio.run(run(args))
    report = {"results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if any(item["errors"] for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
