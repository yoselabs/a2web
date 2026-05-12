"""a2web domain-coupled glue.

Functions that read `AppSettings` or domain models but are too small
to deserve their own module. Lives at the top level of the package
because the previous seam directories (`cache/`, `gate/`, `extract/`,
`log/`, `proxy/`) have been deleted — there's no natural per-domain
home for these.

Pure functions only. No I/O. No class state.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .settings import AppSettings

__all__ = (
    "compute_profile_hash",
    "is_live_only",
)


def compute_profile_hash(settings: AppSettings) -> str:
    """Hash settings fields that affect upstream request shape.

    Fed into `(url, profile_hash)` cache keys so a UA change or stealth
    toggle invalidates cached entries without manual eviction.
    """
    payload = f"{settings.default_ua}|{settings.stealth}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def is_live_only(url: str, settings: AppSettings) -> bool:
    """Return True if `url`'s host should bypass the cache entirely."""
    host = urlparse(url).hostname or ""
    return any(host == h or host.endswith(f".{h}") for h in settings.live_only_hosts)
