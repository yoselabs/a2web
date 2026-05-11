"""a2web routers — `WebRouter` exposes the single `fetch` tool."""

from __future__ import annotations

from typing import Annotated

import a2kit

from .fetcher import fetch as orchestrate
from .models import FetchResponse
from .state import AppState


class WebRouter(a2kit.Router):
    """Routes web-fetch tools. CLI surface: `a2web web <tool>`."""

    @a2kit.read(
        idempotent=True,
        open_world=True,
        title="Fetch Web Page",
    )
    async def fetch(
        self,
        *,
        url: Annotated[str, a2kit.Param(description="Absolute http(s) URL to fetch.")],
        state: AppState,
        ctx: a2kit.ToolContext,
    ) -> FetchResponse:
        """Fetch web content via an adaptive cascade with diagnostic trace.

        Tries site-specific handlers first (Reddit, Hacker News, arxiv,
        Wikipedia, GitHub), then raw HTTP via curl_cffi (TLS-impersonated),
        then jina.ai's reader. Escalates to web.archive.org snapshots when
        the gate detects paywalls or block pages, and to a Camoufox headless
        browser when the gate flags JS-required / proof-of-work / anti-bot
        signals.

        Returns extracted markdown content plus a structured diagnostic trace
        describing every tier attempted, every gate verdict, and timing for
        each phase. Always returns a response — failures are encoded in
        `status` / `verdict` (paywall, block_page_detected, anti_bot, etc.),
        never raised. Block pages NEVER enter the cache.

        Emits typed events on a2kit's LDD channel during the fetch — agents
        and observers can subscribe to phase boundaries and slow-tier
        heartbeats for live visibility.
        """
        return await orchestrate(url, state=state, ctx=ctx)
