"""
Web interface module for the PDF Scraper application.
"""

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import Forbidden, NotFound, TooManyRequests, InternalServerError
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_wtf.csrf import CSRFError, CSRFProtect


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Initialize CSRF protection
    csrf = CSRFProtect(app)

    # Load configuration
    from app.config import Config
    app.config["SECRET_KEY"] = Config.SECRET_KEY

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

    # Initialize rate limiter
    from app.web.limiter import limiter
    limiter.init_app(app)

    # Register routes via modular blueprints
    from app.web.blueprints import register_blueprints
    register_blueprints(app)

    # Exempt API blueprints from CSRF protection — all routes in these
    # blueprints are protected by HTTP Basic Auth (non-cookie), enforced by
    # the app-level before_request handler. No session cookies are used.
    from app.web.blueprints.api_scrapers import bp as api_bp
    csrf.exempt(api_bp)
    from app.web.blueprints.search import bp as search_bp
    csrf.exempt(search_bp)

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'self'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "object-src 'none'"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    def _wants_json():
        return (
            request.accept_mimetypes.best_match(["application/json", "text/html"])
            == "application/json"
        )

    @app.errorhandler(Forbidden)
    def handle_403(exc):
        if _wants_json():
            return jsonify({"error": "Forbidden"}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(NotFound)
    def handle_404(exc):
        if _wants_json():
            return jsonify({"error": "Not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(TooManyRequests)
    def handle_429(exc):
        retry_after = None
        if exc.response is not None:
            retry_after = exc.response.headers.get("Retry-After")
        if retry_after is None:
            retry_after = exc.description if isinstance(exc.description, str) and exc.description.isdigit() else None

        if _wants_json():
            response = jsonify({"error": "Too many requests"})
            if retry_after:
                response.headers["Retry-After"] = retry_after
            return response, 429
        response = app.make_response(render_template("errors/429.html"))
        response.status_code = 429
        if retry_after:
            response.headers["Retry-After"] = retry_after
        return response

    @app.errorhandler(InternalServerError)
    def handle_500(exc):
        if _wants_json():
            return jsonify({"error": "Internal server error"}), 500
        return render_template("errors/500.html"), 500

    @app.errorhandler(CSRFError)
    def handle_csrf_error(exc):
        if _wants_json():
            return jsonify({"error": "CSRF validation failed"}), 400
        return render_template("errors/csrf.html"), 400

    return app
