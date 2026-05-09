"""LogRecord — canonical per-fetch log shape. One JSON object per fetch."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from ..models import FetchResponse


def _dominant_verdict(diagnostics: list[dict]) -> str:
    """Pick the most informative verdict across diagnostic rows.

    Order of precedence: any non-`ok` verdict wins over `ok`. Last
    non-`ok` value (chronologically last in the list) is the most
    actionable signal.
    """
    non_ok = [d for d in diagnostics if d.get("verdict") not in (None, "ok")]
    if non_ok:
        return str(non_ok[-1]["verdict"])
    return "ok"


@dataclass(slots=True)
class LogRecord:
    ts: str
    url: str
    final_url: str
    host: str
    tier: str
    status: str
    verdict: str
    cache: str
    total_ms: int
    content_chars: int
    diagnostics: list[dict] = field(default_factory=list)
    title: str | None = None
    error: str | None = None

    def to_json(self) -> str:
        """Single-line JSON encoding, no embedded newlines."""
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)


def from_response(
    response: FetchResponse,
    *,
    input_url: str | None = None,
    error: str | None = None,
) -> LogRecord:
    """Derive a `LogRecord` from a `FetchResponse`.

    `input_url` allows preserving the user-supplied URL when the response
    carries the post-redirect `final_url`; defaults to `response.url`.
    `error` is populated only on pathological extract/log paths.
    """
    diagnostics_compact = [
        {
            "step": d.step,
            "verdict": d.verdict.value,
            "dur_ms": d.dur_ms,
        }
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
        verdict=_dominant_verdict(diagnostics_compact),
        cache=response.cache.value,
        total_ms=response.total_ms,
        content_chars=len(response.content_md or ""),
        diagnostics=diagnostics_compact,
        title=response.title,
        error=error,
    )
