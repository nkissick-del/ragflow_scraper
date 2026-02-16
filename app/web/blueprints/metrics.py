"""Prometheus metrics endpoint and middleware."""

from __future__ import annotations

import time

from flask import Blueprint, Response, request
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

bp = Blueprint("metrics", __name__)

# --- Counters ---
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

SCRAPER_RUNS = Counter(
    "scraper_runs_total",
    "Total scraper pipeline runs",
    ["scraper", "status"],
)

DOCUMENTS_PROCESSED = Counter(
    "documents_processed_total",
    "Total documents processed through pipeline",
    ["scraper", "stage"],
)

# --- Histograms ---
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

SCRAPER_DURATION = Histogram(
    "scraper_run_duration_seconds",
    "Scraper pipeline run duration in seconds",
    ["scraper"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

# --- Gauges ---
JOB_QUEUE_DEPTH = Gauge(
    "job_queue_depth",
    "Number of jobs currently in the queue",
)


@bp.route("/metrics")
def metrics():
    """Expose Prometheus metrics. Should NOT require auth."""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


def init_metrics_middleware(app):
    """Register before/after request hooks for HTTP metrics tracking.

    Call this from create_app() after blueprint registration.
    """

    @app.before_request
    def _start_timer():
        request._metrics_start = time.perf_counter()  # type: ignore[attr-defined]

    @app.after_request
    def _record_metrics(response):
        # Skip metrics endpoint itself to avoid recursion
        if request.endpoint == "metrics.metrics":
            return response

        endpoint = request.endpoint or "unknown"
        method = request.method
        status = str(response.status_code)

        HTTP_REQUESTS.labels(method=method, endpoint=endpoint, status=status).inc()

        start = getattr(request, "_metrics_start", None)
        if start is not None:
            duration = time.perf_counter() - start
            HTTP_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

        return response
