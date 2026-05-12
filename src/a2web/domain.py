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
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .packages.ndjson_log import LogRecord, dominant_verdict

if TYPE_CHECKING:
    from .models import FetchResponse
    from .settings import AppSettings

__all__ = (
    "compute_profile_hash",
    "is_live_only",
    "log_from_response",
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


def log_from_response(
    response: FetchResponse,
    *,
    input_url: str | None = None,
    error: str | None = None,
) -> LogRecord:
    """Derive a `LogRecord` from a `FetchResponse`.

    `input_url` preserves the user-supplied URL when the response carries
    the post-redirect `final_url`; defaults to `response.url`.
    `error` is populated only on pathological extract/log paths.
    """
    diagnostics_compact = [{"step": d.step, "verdict": d.verdict.value, "dur_ms": d.dur_ms} for d in response.diagnostics]
    host = urlparse(response.url).hostname or ""
    return LogRecord(
        ts=datetime.now(UTC).isoformat(timespec="milliseconds"),
        url=input_url or response.url,
        final_url=response.url,
        host=host,
        tier=response.tier,
        status=response.status.value,
        verdict=dominant_verdict(diagnostics_compact),
        cache=response.cache.value,
        total_ms=response.total_ms,
        content_chars=len(response.content_md or ""),
        diagnostics=diagnostics_compact,
        title=response.title,
        error=error,
    )
