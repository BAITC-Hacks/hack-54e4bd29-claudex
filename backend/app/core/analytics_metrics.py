"""Low-cardinality observability for aggregate analytics."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import Counter, Histogram

analytics_queries_total = Counter(
    "medsignal_analytics_queries_total",
    "Aggregate analytics operations",
    ("operation", "outcome"),
)
analytics_query_duration_seconds = Histogram(
    "medsignal_analytics_query_duration_seconds",
    "Aggregate analytics operation duration",
    ("operation",),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
analytics_cache_access_total = Counter(
    "medsignal_analytics_cache_access_total",
    "Analytics cache access by result",
    ("endpoint", "result"),
)


@contextmanager
def observe_analytics_query(operation: str) -> Iterator[None]:
    """Measure an allowlisted operation name; never attach request values."""
    started = time.perf_counter()
    try:
        yield
    except Exception:
        analytics_queries_total.labels(operation, "failure").inc()
        raise
    else:
        analytics_queries_total.labels(operation, "success").inc()
    finally:
        analytics_query_duration_seconds.labels(operation).observe(
            time.perf_counter() - started
        )


def record_analytics_cache(endpoint: str, result: str) -> None:
    analytics_cache_access_total.labels(endpoint, result).inc()
