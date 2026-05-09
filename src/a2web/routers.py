"""a2web routers — single `WebRouter` exposing the `fetch` tool.

PR1 ships a stub: the tool returns a placeholder `FetchResponse` so MCP
clients and the CLI can exercise the full envelope shape before any tier,
extractor, or cache lands. Real fetching arrives in PR3+.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import a2kit

from .models import CacheState, Confidence, FetchResponse, FetchStatus


class WebRouter(a2kit.Router):
    """Routes web-fetch tools. CLI surface: `a2web web <tool>`."""

    @a2kit.read()
    async def fetch(self, *, url: str) -> FetchResponse:
        """Fetch content from a URL.

        PR1 stub. Returns a placeholder envelope without any I/O so the
        public shape is wire-visible end-to-end.
        """
        start = time.perf_counter()
        started_at = datetime.now(UTC)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return FetchResponse(
            url=url,
            status=FetchStatus.ok,
            tier="stub",
            confidence=Confidence.low,
            started_at=started_at,
            total_ms=elapsed_ms,
            cache=CacheState.miss,
            narrative="PR1 stub — no fetching implemented yet.",
            content_md="",
        )
