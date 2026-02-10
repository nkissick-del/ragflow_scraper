"""Backward-compatible re-exports. Import from submodules directly for new code."""

from app.scrapers.common_mixins import (  # noqa: F401
    IncrementalStateMixin,
    ExclusionRulesMixin,
    MetadataIOMixin,
    WebDriverLifecycleMixin,
    CloudflareBypassMixin,
    ExclusionAndMetadataMixin,
)
from app.scrapers.download_mixin import HttpDownloadMixin  # noqa: F401
from app.scrapers.flaresolverr_mixin import FlareSolverrPageFetchMixin  # noqa: F401

__all__ = [
    "IncrementalStateMixin",
    "ExclusionRulesMixin",
    "MetadataIOMixin",
    "HttpDownloadMixin",
    "WebDriverLifecycleMixin",
    "CloudflareBypassMixin",
    "ExclusionAndMetadataMixin",
    "FlareSolverrPageFetchMixin",
]
