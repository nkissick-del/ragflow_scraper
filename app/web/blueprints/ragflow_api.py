"""RAGFlow API pass-through endpoints."""

from __future__ import annotations

import functools
from flask import Blueprint, jsonify

from app.services import RAGFlowClient
from app.utils import get_logger

bp = Blueprint("ragflow_api", __name__)
logger = get_logger("web.ragflow_api")


def handle_ragflow_errors(f):
    """
    Decorator to handle RAGFlow API errors consistently.
    
    Logs exceptions and returns a generic error response with 500 status
    instead of exposing internal error details.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as exc:
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
