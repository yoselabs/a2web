"""a2web routers — `WebRouter` exposes the single `fetch` tool.

CLI surface: `a2web web fetch --url=...`.
"""

from __future__ import annotations

import a2kit
import anyio

from .events import EventBus, mcp_progress_sink, otel_sink
from .fetcher import fetch as orchestrate
from .models import FetchResponse
from .state import AppState


class WebRouter(a2kit.Router):
    """Routes web-fetch tools. CLI surface: `a2web web <tool>`."""

    @a2kit.read()
    async def fetch(self, *, url: str, state: AppState, ctx: a2kit.ToolContext) -> FetchResponse:
        """Fetch content from a URL."""
        bus = EventBus()
        mcp_recv = bus.subscribe()
        otel_recv = bus.subscribe()

        async with anyio.create_task_group() as tg:
            tg.start_soon(mcp_progress_sink, ctx, mcp_recv)
            tg.start_soon(otel_sink, otel_recv)
            try:
                response = await orchestrate(url, state=state, bus=bus)
            finally:
                await bus.aclose()
        return response
