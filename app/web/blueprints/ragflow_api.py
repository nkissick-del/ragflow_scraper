"""RAGFlow API pass-through endpoints."""

from __future__ import annotations

import functools
from flask import Blueprint, jsonify
import requests

from app.services import RAGFlowClient
from app.utils import get_logger
from app.utils.errors import ValidationError, ConfigurationError

bp = Blueprint("ragflow_api", __name__)
logger = get_logger("web.ragflow_api")


def handle_ragflow_errors(f):
    """
    Decorator to handle RAGFlow API errors consistently.
    
    Maps specific exception types to appropriate HTTP status codes:
    - Authentication errors (401)
    - Bad request/validation errors (400)
    - Not found errors (404)
    - Other errors (500)
    
    Logs exceptions and returns a generic error response.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except requests.HTTPError as exc:
            # Map HTTP errors from RAGFlow API to appropriate status codes
            logger.exception(f"Error in {f.__name__}")
            status_code = 500
            if exc.response is not None:
                if exc.response.status_code == 401 or exc.response.status_code == 403:
                    status_code = 401
                elif exc.response.status_code == 400:
                    status_code = 400
                elif exc.response.status_code == 404:
                    status_code = 404
                elif 400 <= exc.response.status_code < 500:
                    # Other client errors
                    status_code = exc.response.status_code
            return jsonify({"success": False, "error": "Operation failed"}), status_code
        except ValidationError:
            # Validation errors from our code
            logger.exception(f"Error in {f.__name__}")
            return jsonify({"success": False, "error": "Operation failed"}), 400
        except ConfigurationError:
            # Configuration errors (authentication issues, etc.)
            logger.exception(f"Error in {f.__name__}")
            return jsonify({"success": False, "error": "Operation failed"}), 401
        except Exception:
            # All other unexpected exceptions
            logger.exception(f"Error in {f.__name__}")
            return jsonify({"success": False, "error": "Operation failed"}), 500
    return wrapper


@bp.route("/api/ragflow/models", methods=["GET"])
@handle_ragflow_errors
def get_ragflow_models():
    client = RAGFlowClient()
    models = client.list_embedding_models()
    return jsonify({"success": True, "models": models})


@bp.route("/api/ragflow/chunk-methods", methods=["GET"])
@handle_ragflow_errors
def get_ragflow_chunk_methods():
    client = RAGFlowClient()
    methods = client.list_chunk_methods()
    return jsonify({"success": True, "methods": methods})
