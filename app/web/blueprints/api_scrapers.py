"""API endpoints for scraper management."""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.scrapers import ScraperRegistry

bp = Blueprint("api_scrapers", __name__)


@bp.route("/api/scrapers")
def api_list_scrapers():
    scrapers = ScraperRegistry.list_scrapers()
    return jsonify({"scrapers": scrapers})


@bp.route("/api/scrapers/<name>/run", methods=["POST"])
def api_run_scraper(name):
    scraper = ScraperRegistry.get_scraper(name)
    if not scraper:
        return jsonify({"error": f"Scraper not found: {name}"}), 404

    result = scraper.run()
    return jsonify(result.to_dict())
