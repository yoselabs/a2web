"""a2web routers — single `WebRouter` exposing the `fetch` tool."""

from __future__ import annotations

import a2kit

from .fetcher import fetch as orchestrate
from .models import FetchResponse
from .state import AppState


class WebRouter(a2kit.Router):
    """Routes web-fetch tools. CLI surface: `a2web web <tool>`."""

    @a2kit.read()
    async def fetch(self, *, url: str, state: AppState) -> FetchResponse:
        """Fetch content from a URL.

        One call runs the full v0.1 cascade — cache check, tier loop,
        extraction, quality gate, cache write — and returns the best
        content obtainable plus a structured diagnostic trace.
        """
        return await orchestrate(url, state=state)
