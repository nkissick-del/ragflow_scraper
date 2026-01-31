"""
Web interface module for the PDF Scraper application.
"""

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

csrf = CSRFProtect()


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Load configuration
    from app.config import Config
    app.config["SECRET_KEY"] = Config.SECRET_KEY

    # Initialize CSRF protection
    csrf.init_app(app)

    # Respect proxy headers when running behind reverse proxies (controlled via TRUST_PROXY_COUNT)
    if Config.TRUST_PROXY_COUNT > 0:
        app.wsgi_app = ProxyFix(  # type: ignore[assignment]
            app.wsgi_app,
            x_for=Config.TRUST_PROXY_COUNT,
            x_proto=Config.TRUST_PROXY_COUNT,
            x_host=Config.TRUST_PROXY_COUNT,
            x_port=Config.TRUST_PROXY_COUNT,
            x_prefix=Config.TRUST_PROXY_COUNT,
        )

    # Register routes via modular blueprints
    from app.web.blueprints import register_blueprints
    register_blueprints(app)

    return app
