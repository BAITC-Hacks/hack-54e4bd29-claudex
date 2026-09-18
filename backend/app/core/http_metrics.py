"""Low-cardinality HTTP and background-job Prometheus metrics."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

http_requests_total = Counter(
    "medsignal_http_requests_total",
    "HTTP requests by method, route template and status",
    ("method", "route", "status"),
)
http_request_duration_seconds = Histogram(
    "medsignal_http_request_duration_seconds",
    "HTTP request duration by method and route template",
    ("method", "route"),
)
background_jobs_total = Counter(
    "medsignal_background_jobs_total",
    "Background jobs by bounded task name and outcome",
    ("task", "outcome"),
)


def route_label(scope: Mapping[str, Any]) -> str:
    """Return Starlette's route template, never the concrete request path."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else "unmatched"


def record_background_job(task: str, outcome: str) -> None:
    background_jobs_total.labels(task=task, outcome=outcome).inc()


class HttpMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = route_label(request.scope)
            method = request.method
            http_requests_total.labels(
                method=method, route=route, status=str(status)
            ).inc()
            http_request_duration_seconds.labels(method=method, route=route).observe(
                time.perf_counter() - started
            )
