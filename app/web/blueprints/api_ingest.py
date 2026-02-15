"""API endpoints for RAG re-ingestion."""

from __future__ import annotations

import re

from flask import Blueprint, jsonify, request

from app.config import Config
from app.services.reconciliation import ReconciliationService
from app.utils import get_logger
from app.web.limiter import limiter
from app.web.runtime import container

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

bp = Blueprint("api_ingest", __name__)
logger = get_logger("web.api_ingest")


@bp.route("/api/ingest/sync/<scraper_name>", methods=["POST"])
@limiter.limit("5/minute")
def api_ingest_sync(scraper_name: str):
    """
    Re-ingest documents for a scraper that are in Paperless but missing from RAG.

    Request body (JSON):
        dry_run (bool): If true, only report which documents would be synced.
                        Defaults to true for safety.

    Returns:
        JSON with synced_urls, count, and dry_run flag.
    """
    if not _NAME_RE.match(scraper_name):
        return jsonify({"error": "Invalid scraper name format"}), 400

    json_data = request.get_json(silent=True) or {}
    dry_run = json_data.get("dry_run", True)

    try:
        recon = ReconciliationService(container=container)
        synced_urls = recon.sync_rag_gaps(scraper_name, dry_run=dry_run)

        return jsonify({
            "synced_urls": synced_urls,
            "count": len(synced_urls),
            "dry_run": dry_run,
        }), 200

    except RuntimeError as exc:
        logger.error(f"Ingest sync failed for {scraper_name}: {exc}")
        return jsonify({"error": str(exc)}), 503

    except Exception as exc:
        logger.error(f"Ingest sync error for {scraper_name}: {exc}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/api/ingest/documents", methods=["POST"])
@limiter.limit("5/minute")
def api_ingest_documents():
    """
    Re-ingest specific Paperless documents by ID into the RAG backend.

    Request body (JSON):
        document_ids (list[int]): Paperless document IDs to re-ingest.
        source (str): Source label for metadata. Defaults to "manual".

    Returns:
        JSON with per-document results, total, and succeeded count.
    """
    json_data = request.get_json(silent=True) or {}
    document_ids = json_data.get("document_ids")
    source = json_data.get("source", "manual")

    if not document_ids or not isinstance(document_ids, list):
        return jsonify({"error": "document_ids must be a non-empty list"}), 400

    # Validate all IDs are integers
    for doc_id in document_ids:
        if not isinstance(doc_id, int) or doc_id < 1:
            return jsonify({"error": f"Invalid document_id: {doc_id}"}), 400

    try:
        recon = ReconciliationService(container=container)
        client = recon._get_paperless_client()
        dataset_id = Config.RAGFLOW_DATASET_ID or None

        results: list[dict] = []
        succeeded = 0

        for doc_id in document_ids:
            try:
                # Get document metadata from Paperless to find URL
                doc_meta = client.get_document(doc_id)
                url = ""
                if doc_meta:
                    # Try custom fields, then fall back to empty
                    custom_fields = doc_meta.get("custom_fields", [])
                    for cf in custom_fields:
                        if cf.get("field_name") == "source_url" or cf.get("field") == "source_url":
                            url = cf.get("value", "")
                            break
                    if not url:
                        url = f"paperless://document/{doc_id}"

                success = recon._reingest_document(
                    doc_id=doc_id,
                    url=url,
                    source=source,
                    client=client,
                    dataset_id=dataset_id,
                )
                results.append({"document_id": doc_id, "success": success})
                if success:
                    succeeded += 1

            except Exception as exc:
                logger.error(f"Re-ingest failed for document {doc_id}: {exc}")
                results.append({"document_id": doc_id, "success": False, "error": str(exc)})

        return jsonify({
            "results": results,
            "total": len(document_ids),
            "succeeded": succeeded,
        }), 200

    except RuntimeError as exc:
        logger.error(f"Ingest documents failed: {exc}")
        return jsonify({"error": str(exc)}), 503

    except Exception as exc:
        logger.error(f"Ingest documents error: {exc}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
