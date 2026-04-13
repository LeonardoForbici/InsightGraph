"""Performance metrics and Prometheus exports for InsightGraph."""

from __future__ import annotations

import re
import time
from typing import Callable

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUEST_COUNT = Counter(
    "ig_http_requests_total",
    "Total HTTP requests processed by InsightGraph",
    ["method", "path", "status"],
    registry=REGISTRY,
)
HTTP_REQUEST_LATENCY = Histogram(
    "ig_http_request_latency_seconds",
    "Latency of HTTP requests handled by InsightGraph",
    ["method", "path"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY,
)
WEBSOCKET_CONNECTIONS = Gauge(
    "ig_websocket_connections",
    "Active WebSocket connections",
    registry=REGISTRY,
)
EVENT_BATCH_SIZE = Histogram(
    "ig_event_batch_size",
    "Number of impact events flushed together",
    buckets=(1, 5, 10, 25, 50, 100, 250),
    registry=REGISTRY,
)
EVENT_PROPAGATION_LATENCY = Histogram(
    "ig_event_propagation_latency_seconds",
    "Time spent propagating an impact batch",
    ["event_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY,
)
PREDICTION_REQUESTS = Counter(
    "ig_prediction_requests_total",
    "Total number of risk prediction requests",
    registry=REGISTRY,
)

_SANITIZE_PATH_RE = re.compile(r"/\d+(?=/|$)")


def _sanitize_path(path: str) -> str:
    return _SANITIZE_PATH_RE.sub("/:id", path)


def record_http_request(method: str, path: str, status: int, duration: float) -> None:
    sanitized = _sanitize_path(path)
    HTTP_REQUEST_COUNT.labels(method=method, path=sanitized, status=str(status)).inc()
    HTTP_REQUEST_LATENCY.labels(method=method, path=sanitized).observe(duration)


def increment_websocket_connections() -> None:
    WEBSOCKET_CONNECTIONS.inc()


def decrement_websocket_connections() -> None:
    WEBSOCKET_CONNECTIONS.dec()


def observe_event_batch(size: int) -> None:
    EVENT_BATCH_SIZE.observe(max(0, size))


def record_event_latency(event_type: str, duration: float) -> None:
    if duration < 0:
        duration = 0
    EVENT_PROPAGATION_LATENCY.labels(event_type=event_type).observe(duration)


def record_prediction_request() -> None:
    PREDICTION_REQUESTS.inc()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that captures HTTP workload metrics."""

    async def dispatch(self, request: Request, call_next: Callable):
        start = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration = time.monotonic() - start
            record_http_request(request.method, str(request.url.path), status, duration)


def metrics_response() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
