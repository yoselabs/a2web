"""a2web seam — `LogRecord` re-export + domain-coupled constructors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ..packages.ndjson_log import LogRecord, dominant_verdict

if TYPE_CHECKING:
    from ..models import FetchResponse

__all__ = ("LogRecord", "from_response")


def from_response(
    response: FetchResponse,
    *,
    input_url: str | None = None,
    error: str | None = None,
) -> LogRecord:
    """Derive a `LogRecord` from a `FetchResponse`."""
    diagnostics_compact = [
        {"step": d.step, "verdict": d.verdict.value, "dur_ms": d.dur_ms}
        for d in response.diagnostics
    ]
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
