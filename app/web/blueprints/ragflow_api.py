"""RAGFlow API pass-through endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.services import RAGFlowClient

bp = Blueprint("ragflow_api", __name__)


@bp.route("/api/ragflow/models", methods=["GET"])
def get_ragflow_models():
    try:
        client = RAGFlowClient()
        models = client.list_embedding_models()
        return jsonify({"success": True, "models": models})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)})


@bp.route("/api/ragflow/chunk-methods", methods=["GET"])
def get_ragflow_chunk_methods():
    try:
        client = RAGFlowClient()
        methods = client.list_chunk_methods()
        return jsonify({"success": True, "methods": methods})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)})
