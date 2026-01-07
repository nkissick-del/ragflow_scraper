"""Blueprint registration."""

from __future__ import annotations

from flask import Flask

from app.web.blueprints import auth, scrapers, settings, metrics_logs, ragflow_api, api_scrapers


def register_blueprints(app: Flask) -> None:
    """Register all application blueprints.
    
    Note: auth.bp uses @bp.before_app_request to apply basic auth globally.
    All other blueprints provide modular route functionality.
    """
    app.register_blueprint(auth.bp)
    app.register_blueprint(scrapers.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(metrics_logs.bp)
    app.register_blueprint(ragflow_api.bp)
    app.register_blueprint(api_scrapers.bp)
