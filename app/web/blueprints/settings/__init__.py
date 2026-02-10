"""Settings blueprint package.

Provides three sub-blueprints (ui, api, reconciliation) and a backward-compatible
``bp`` that can be used by the old ``register_blueprints()`` pattern while also
exposing the list for future per-blueprint registration.
"""

from __future__ import annotations

from app.web.blueprints.settings.ui import bp as ui_bp
from app.web.blueprints.settings.api import bp as api_bp
from app.web.blueprints.settings.reconciliation import bp as recon_bp

# Backward-compatible re-exports used by tests (e.g. test_ssrf_validation.py)
from app.web.blueprints.settings.helpers import _validate_url_ssrf  # noqa: F401

blueprints = [ui_bp, api_bp, recon_bp]

# Backward compatibility: ``from app.web.blueprints import settings; settings.bp``
# The old code registered a single ``settings.bp``.  We keep the name so the
# existing ``register_blueprints`` in ``__init__.py`` doesn't break, but now it
# returns the first blueprint.  The caller is updated to iterate ``blueprints``.
bp = ui_bp
