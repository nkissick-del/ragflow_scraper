"""
Web interface module for the PDF Scraper application.
"""

from flask import Flask


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

    # Register routes
    from app.web.routes import bp
    app.register_blueprint(bp)

    return app
