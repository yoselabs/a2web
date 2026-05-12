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
        url: Annotated[str, a2kit.Param("Absolute http(s) URL to fetch.")],
        include_links: Annotated[
            bool,
            a2kit.Param(
                description=(
                    "Include the extracted `links` array in the response. Default "
                    "False — links are a large share of payload bytes on aggregator "
                    "pages (HN, PyPI, GitHub trending) and most tasks don't need them. "
                    "Pass True for list-extraction tasks."
                ),
            ),
        ] = False,
        link_roles: Annotated[
            list[str] | None,
            a2kit.Param(
                description=(
                    "When include_links=True, filter to these DOM roles. Choices: "
                    "'primary' (article body, default), 'nav', 'meta' (header/aside), "
                    "'footer'. Pass None to keep everything (verbose). Defaults to "
                    "['primary'] — kills nav/footer bloat that's typically 60-80%% of "
                    "link entries on real pages."
                ),
            ),
        ] = None,
        debug: Annotated[
            bool,
            a2kit.Param(
                description=(
                    "Return the full `diagnostics` trace and per-tier rows. Default "
                    "False — a one-line `diagnostics_summary` is always populated. "
                    "Pass True for debugging fetch behavior."
                ),
            ),
        ] = False,
        wrap_content: Annotated[
            bool,
            a2kit.Param(
                description=(
                    "Wrap content_md with HTML-comment markers carrying source "
                    "URL + fetched_at + 'untrusted content' warning. Default True. "
                    "Defensive cue for agents — invisible in rendered HTML/markdown, "
                    "readable to LLMs scanning the raw string. Pass False for raw "
                    "content (e.g. piping to a renderer that strips comments)."
                ),
            ),
        ] = True,
        ask: Annotated[
            str | None,
            a2kit.Param(
                description=(
                    "Optional question to answer about the fetched page. When set, "
                    "a2web invokes an LLM extractor server-side over the fetched "
                    "content and populates `extracted_answer` + `extraction` "
                    "metadata. Mirrors Claude Code WebFetch's behavior — keeps the "
                    "calling agent's context tiny. Requires the `[llm]` install "
                    "extra and a configured API key; without those the fetch still "
                    "succeeds but `extracted_answer` is None and an operator hint "
                    "is recorded."
                ),
            ),
        ] = None,
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
        roles_filter = frozenset(link_roles) if link_roles is not None else frozenset({"primary"})
        return await orchestrate(
            url,
            state=state,
            ctx=ctx,
            include_links=include_links,
            link_roles=roles_filter,
            wrap_content=wrap_content,
            debug=debug,
            ask=ask,
        )
