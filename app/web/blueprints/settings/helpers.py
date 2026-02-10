"""Shared helpers for settings blueprints."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from app.utils.logging_config import log_event, log_exception
from app.utils import get_logger
from app.web.runtime import container

logger = get_logger("web.settings")

# Input validation limits
_MAX_URL_LENGTH = 2048
_MAX_FIELD_LENGTH = 255
_MAX_TEMPLATE_LENGTH = 1024

# Cloud metadata / link-local networks to block (SSRF mitigation).
# Private RFC1918 ranges (10.x, 172.16-31.x, 192.168.x) are intentionally
# ALLOWED because this self-hosted app connects to local-network services.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]


def _check_service_status(check_fn, service_name: str) -> str:
    """Run a health check function and return status string."""
    try:
        if check_fn():
            return "connected"
        return "disconnected"
    except Exception as exc:
        log_exception(logger, exc, f"{service_name}.connection.error", page="settings")
        return "error"


def _get_effective_url(service: str, config_attr: str) -> str:
    """Get effective service URL from settings override or Config fallback."""
    from app.config import Config
    override = container.settings.get(f"services.{service}_url", "")
    if override:
        return override
    return getattr(Config, config_attr, "")


def _get_effective_timeout(service: str, config_attr: str) -> int:
    """Get effective timeout from settings override (if >0) or Config fallback."""
    from app.config import Config
    override = container.settings.get(f"services.{service}_timeout", 0)
    if override and override > 0:
        return override
    return getattr(Config, config_attr, 60)


def _get_effective_backend(backend_type: str) -> str:
    """Get effective backend name from settings override or Config fallback."""
    from app.config import Config
    override = container.settings.get(f"pipeline.{backend_type}_backend", "")
    if override:
        return override
    return getattr(Config, f"{backend_type.upper()}_BACKEND", "")


def _validate_url_ssrf(url: str) -> str | None:
    """Return an error message if *url* targets a blocked address, else None."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return "URL has no hostname"

        # Resolve hostname to IP(s) and check each
        infos = socket.getaddrinfo(hostname, parsed.port or 80, proto=socket.IPPROTO_TCP)
        for _family, _type, _proto, _canonname, sockaddr in infos:
            addr = ipaddress.ip_address(sockaddr[0])
            for net in _BLOCKED_NETWORKS:
                if addr in net:
                    return f"URL resolves to a blocked address range ({net})"
    except socket.gaierror:
        log_event(logger, "warning", "ssrf.dns_resolution_failed",
                  hostname=hostname, url=url)
        return f"URL hostname '{hostname}' could not be resolved (DNS failure)"
    except Exception:
        return "URL could not be validated"
    return None


def _validate_scraper_name(name: str) -> bool:
    """Validate scraper name to prevent injection."""
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))
