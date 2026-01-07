"""API endpoints for scraper management."""

from __future__ import annotations

import re
from flask import Blueprint, jsonify, request

from app.scrapers import ScraperRegistry
from app.utils import get_logger
from app.utils.errors import ScraperAlreadyRunningError
from app.web.runtime import job_queue

bp = Blueprint("api_scrapers", __name__)
logger = get_logger("web.api_scrapers")


@bp.route("/api/scrapers")
def api_list_scrapers():
    scrapers = ScraperRegistry.list_scrapers()
    return jsonify({"scrapers": scrapers})


@bp.route("/api/scrapers/<name>/run", methods=["POST"])
def api_run_scraper(name):
    """
    Run a scraper asynchronously via job queue.
    
    Returns a job ID for status polling.
    Authentication is enforced at the app level via auth.py blueprint.
    """
    # Validate and sanitize scraper name (alphanumeric, hyphens, underscores only)
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        logger.warning(f"Invalid scraper name attempted: {name}")
        return jsonify({"error": "Invalid scraper name format"}), 400
    
    # Parse optional parameters
    dry_run = request.json.get("dry_run", False) if request.is_json else False
    max_pages = request.json.get("max_pages") if request.is_json else None
    
    # Validate max_pages if provided
    if max_pages is not None:
        try:
            max_pages = int(max_pages)
            if max_pages < 1:
                return jsonify({"error": "max_pages must be >= 1"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "max_pages must be an integer"}), 400
    
    # Get scraper instance
    try:
        scraper = ScraperRegistry.get_scraper(name, dry_run=dry_run, max_pages=max_pages)
    except Exception as exc:
        logger.error(f"Error getting scraper {name}: {exc}", exc_info=True)
        return jsonify({"error": "Failed to initialize scraper"}), 500
    
    if not scraper:
        return jsonify({"error": f"Scraper not found: {name}"}), 404
    
    # Enqueue job for background execution
    try:
        job = job_queue.enqueue(name, scraper, dry_run=dry_run, max_pages=max_pages)
        logger.info(f"API: Enqueued scraper {name} (dry_run={dry_run}, max_pages={max_pages})")
        
        return jsonify({
            "success": True,
            "job_id": name,  # Job ID is the scraper name (one job per scraper)
            "status": "queued",
            "message": f"Scraper {name} queued for execution"
        }), 202
        
    except ScraperAlreadyRunningError:
        return jsonify({
            "error": f"Scraper {name} is already running",
            "status": "running"
        }), 409
        
    except Exception as exc:
        logger.error(f"Error enqueueing scraper {name}: {exc}", exc_info=True)
        return jsonify({"error": "Failed to queue scraper"}), 500


@bp.route("/api/scrapers/<name>/status", methods=["GET"])
def api_scraper_status(name):
    """
    Get the status of a scraper job.
    
    Returns job status, result if completed, or error if failed.
    """
    # Validate scraper name
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({"error": "Invalid scraper name format"}), 400
    
    try:
        job = job_queue.get(name)
        
        if not job:
            return jsonify({
                "error": f"No job found for scraper: {name}",
                "status": "not_found"
            }), 404
        
        response = {
            "job_id": name,
            "status": job.status,
            "preview": job.preview,
            "dry_run": job.dry_run,
            "max_pages": job.max_pages,
            "started_at": job.started_at if job.started_at else None,
            "completed_at": job.completed_at if job.completed_at else None,
        }
        
        # Include result if completed
        if job.status == "completed" and job.result:
            try:
                # Validate result has to_dict before calling
                if hasattr(job.result, "to_dict") and callable(job.result.to_dict):
                    response["result"] = job.result.to_dict()
                else:
                    logger.warning(f"Job result for {name} has no to_dict method")
                    response["result"] = {"status": "completed"}
            except Exception as exc:
                logger.error(f"Error serializing result for {name}: {exc}", exc_info=True)
                response["result"] = {"status": "completed", "serialization_error": True}
        
        # Include error if failed
        if job.status == "failed" and job.error:
            response["error"] = str(job.error)
        
        return jsonify(response), 200
        
    except Exception as exc:
        logger.error(f"Error getting status for {name}: {exc}", exc_info=True)
        return jsonify({"error": "Failed to retrieve job status"}), 500
