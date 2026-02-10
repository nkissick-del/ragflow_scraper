"""Settings reconciliation routes."""

from __future__ import annotations

from flask import Blueprint
from markupsafe import escape

from app.utils.logging_config import log_exception
from app.web.runtime import container
from app.web.blueprints.settings.helpers import (
    logger,
    _validate_scraper_name,
)

bp = Blueprint("settings_recon", __name__)


@bp.route("/settings/reconciliation/report/<name>", methods=["POST"])
def reconciliation_report(name: str):
    if not _validate_scraper_name(name):
        return '<div class="alert alert-danger">Invalid scraper name</div>'

    try:
        from app.services.reconciliation import ReconciliationService

        recon = ReconciliationService(container=container)
        report = recon.get_report(name)

        errors_html = ""
        if report.errors:
            errors_html = '<ul class="text-warning">'
            for err in report.errors:
                errors_html += f"<li>{escape(err)}</li>"
            errors_html += "</ul>"

        only_state_html = ""
        if report.urls_only_in_state:
            only_state_html = f'<details><summary>{len(report.urls_only_in_state)} URLs only in state</summary><ul>'
            for url in report.urls_only_in_state[:50]:
                only_state_html += f"<li><code>{escape(url)}</code></li>"
            if len(report.urls_only_in_state) > 50:
                only_state_html += f"<li>... and {len(report.urls_only_in_state) - 50} more</li>"
            only_state_html += "</ul></details>"

        only_paperless_html = ""
        if report.urls_only_in_paperless:
            only_paperless_html = f'<details><summary>{len(report.urls_only_in_paperless)} URLs only in Paperless</summary><ul>'
            for url in report.urls_only_in_paperless[:50]:
                only_paperless_html += f"<li><code>{escape(url)}</code></li>"
            if len(report.urls_only_in_paperless) > 50:
                only_paperless_html += f"<li>... and {len(report.urls_only_in_paperless) - 50} more</li>"
            only_paperless_html += "</ul></details>"

        rag_gaps_html = ""
        if report.urls_in_paperless_not_rag:
            rag_gaps_html = f'<details><summary>{len(report.urls_in_paperless_not_rag)} URLs in Paperless but not RAG</summary><ul>'
            for url in report.urls_in_paperless_not_rag[:50]:
                rag_gaps_html += f"<li><code>{escape(url)}</code></li>"
            if len(report.urls_in_paperless_not_rag) > 50:
                rag_gaps_html += f"<li>... and {len(report.urls_in_paperless_not_rag) - 50} more</li>"
            rag_gaps_html += "</ul></details>"

        return f'''
            <div class="alert alert-info">
                <strong>Reconciliation Report: {escape(name)}</strong>
                <table class="mt-2" style="width: auto;">
                    <tr><td>State URLs:</td><td><strong>{report.state_url_count}</strong></td></tr>
                    <tr><td>Paperless URLs:</td><td><strong>{report.paperless_url_count}</strong></td></tr>
                    <tr><td>RAG Documents:</td><td><strong>{report.rag_document_count}</strong></td></tr>
                </table>
                {errors_html}
                {only_state_html}
                {only_paperless_html}
                {rag_gaps_html}
            </div>
        '''
    except Exception as exc:
        log_exception(logger, exc, "reconciliation.report.error")
        return f'<div class="alert alert-danger">Report failed: {escape(str(exc))}</div>'


@bp.route("/settings/reconciliation/rebuild/<name>", methods=["POST"])
def reconciliation_rebuild(name: str):
    if not _validate_scraper_name(name):
        return '<div class="alert alert-danger">Invalid scraper name</div>'

    try:
        from app.services.reconciliation import ReconciliationService

        recon = ReconciliationService(container=container)
        added = recon.rebuild_state(name)

        return f'''
            <div class="alert alert-success">
                State rebuilt for {escape(name)}: {added} URLs added from Paperless
            </div>
        '''
    except Exception as exc:
        log_exception(logger, exc, "reconciliation.rebuild.error")
        return f'<div class="alert alert-danger">Rebuild failed: {escape(str(exc))}</div>'


@bp.route("/settings/reconciliation/sync-rag/<name>", methods=["POST"])
def reconciliation_sync_rag(name: str):
    if not _validate_scraper_name(name):
        return '<div class="alert alert-danger">Invalid scraper name</div>'

    try:
        from app.services.reconciliation import ReconciliationService

        recon = ReconciliationService(container=container)
        re_ingested = recon.sync_rag_gaps(name, dry_run=False)

        if re_ingested:
            urls_html = "<ul>"
            for url in re_ingested[:20]:
                urls_html += f"<li><code>{escape(url)}</code></li>"
            if len(re_ingested) > 20:
                urls_html += f"<li>... and {len(re_ingested) - 20} more</li>"
            urls_html += "</ul>"
            return f'''
                <div class="alert alert-success">
                    RAG sync complete: {len(re_ingested)} documents re-ingested
                    {urls_html}
                </div>
            '''
        else:
            return '''
                <div class="alert alert-info">
                    No documents needed re-ingestion. RAG is in sync with Paperless.
                </div>
            '''
    except Exception as exc:
        log_exception(logger, exc, "reconciliation.sync_rag.error")
        return f'<div class="alert alert-danger">RAG sync failed: {escape(str(exc))}</div>'
