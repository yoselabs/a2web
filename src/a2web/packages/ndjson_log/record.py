"""LogRecord — canonical per-fetch log shape. One JSON object per fetch.

Boundary type owned by the `ndjson_log` package. Construction from
domain types (e.g. `a2web.models.FetchResponse`) lives at the a2web
seam.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


def dominant_verdict(diagnostics: list[dict]) -> str:
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
