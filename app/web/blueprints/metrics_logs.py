"""Metrics and log endpoints."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, render_template, Response
from markupsafe import escape

from app.config import Config
from app.scrapers import ScraperRegistry
from app.utils.logging_config import log_event, log_exception
from app.utils import get_logger
from app.web.runtime import container

bp = Blueprint("metrics_logs", __name__)
logger = get_logger("web.metrics")


@bp.route("/logs")
def logs():
    log_files = sorted(
        Config.LOG_DIR.glob("*.log"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )[:10]

    log_event(logger, "info", "ui.page.logs", file_count=len(log_files))
    return render_template("logs.html", log_files=log_files)


@bp.route("/logs/stream")
def log_stream():
    log_files = sorted(Config.LOG_DIR.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not log_files:
        return ""

    try:
        with open(log_files[0]) as f:
            lines = f.readlines()[-50:]

        level_to_css = {
            "CRITICAL": "log-error",
            "ERROR": "log-error",
            "WARNING": "log-warning",
            "DEBUG": "log-debug",
            "INFO": "log-info",
        }

        html = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                time_str = escape(entry.get("timestamp", ""))
                level = entry.get("level", "INFO").upper()
                logger_name = entry.get("logger", "")
                message = entry.get("message", "")
                display_msg = f"{logger_name} | {message}" if logger_name else message
                css_class = level_to_css.get(level, "log-info")
                html += (
                    f'<div class="log-entry {css_class}">'
                    f'<span class="log-time">{time_str}</span> '
                    f'<span class="log-level">{escape(level)}</span> '
                    f'<span class="log-message">{escape(display_msg)}</span>'
                    f"</div>"
                )
            except (json.JSONDecodeError, AttributeError):
                css_class = "log-info"
                if " ERROR" in line or line.startswith("ERROR"):
                    css_class = "log-error"
                elif " WARNING" in line or line.startswith("WARNING"):
                    css_class = "log-warning"
                elif " DEBUG" in line or line.startswith("DEBUG"):
                    css_class = "log-debug"
                html += f'<div class="log-entry {css_class}">{escape(line)}</div>'

        return html
    except Exception as exc:
        log_exception(logger, exc, "logs.stream.error")
        return f'<div class="log-entry log-error">Error reading logs: {escape(str(exc))}</div>'


@bp.route("/logs/download/<filename>")
def download_log(filename):
    # Validate filename to prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return "Invalid filename", 400
    
    log_path = Config.LOG_DIR / filename
    
    # Additional check: ensure resolved path is still within LOG_DIR
    try:
        log_path.resolve().relative_to(Config.LOG_DIR.resolve())
    except (ValueError, OSError):
        return "Invalid filename", 400
    
    if not log_path.exists() or not log_path.is_file():
        return "Not found", 404

    try:
        with open(log_path) as f:
            content = f.read()
    except Exception as exc:
        log_exception(logger, exc, "logs.download.error", filename=filename)
        return "Not found", 404

    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/metrics/flaresolverr")
def flaresolverr_metrics():
    try:
        flaresolverr = container.flaresolverr_client
        metrics = flaresolverr.get_metrics()
        log_event(logger, "info", "metrics.flaresolverr.success", metrics=metrics)
        return jsonify(metrics)
    except Exception as exc:
        log_exception(logger, exc, "metrics.flaresolverr.error")
        return jsonify({"success": 0, "failure": 0, "timeout": 0, "total": 0, "success_rate": 0.0})


@bp.route("/metrics/pipeline")
def pipeline_metrics():
    metrics: list[dict] = []
    total_processed = 0
    total_failed = 0

    scrapers = ScraperRegistry.list_scrapers()
    names = [s["name"] for s in scrapers if isinstance(s.get("name"), str)]

    # Batch-fetch all scrapers' state in one DB round-trip
    all_info: dict = {}
    store = container._get_state_store()
    if store is not None and hasattr(store, "get_all_last_run_info"):
        try:
            all_info = store.get_all_last_run_info(names)
        except Exception:
            pass

    for name in names:
        last_run = all_info.get(name)
        if last_run is None:
            # Fallback: per-scraper query
            try:
                state = container.state_tracker(name)
                last_run = state.get_last_run_info() or {}
            except Exception:
                last_run = {}
        processed = last_run.get("processed_count", 0)
        failed = last_run.get("failed_count", 0)
        total_processed += processed
        total_failed += failed
        metrics.append(
            {
                "scraper": name,
                "last_run": last_run.get("last_updated"),
                "processed_count": processed,
                "failed_count": failed,
                "status": last_run.get("status", "unknown"),
            }
        )

    log_event(
        logger,
        "info",
        "metrics.pipeline.snapshot",
        scraper_count=len(metrics),
        total_processed=total_processed,
        total_failed=total_failed,
    )
    return jsonify({
        "scrapers": metrics,
        "totals": {
            "processed": total_processed,
            "failed": total_failed,
        },
    })
