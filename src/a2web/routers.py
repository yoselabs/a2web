"""a2web routers — `WebRouter` exposes `ask` + `fetch_raw`; `CookiesRouter` exposes `refresh`.

v0.7 split: the single `fetch` tool became two tools so the agent surface
itself enforces the cost-discipline preference. `ask` requires a question
and always runs the server-side LLM extractor (Haiku 4.5 by default) —
this is the primary tool, intended for ~95%% of web reads. `fetch_raw`
returns content with no LLM step and is documented as a fallback.

Both tools delegate to the same orchestrator (`fetcher.fetch`); the only
difference is whether `ask=` is passed through.

When `settings.ask_only` is true (env `A2WEB_ASK_ONLY=true` or
`--ask-only` on `serve`), only `ask` is registered on the MCP/CLI
surface. The toggle is a stop-gap until a2kit absorbs proper tool
selection — tracked in `docs/history/A2KIT_FEEDBACK_v0.39.md`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, ClassVar

import a2kit
import pydantic
from a2kit.packages.di import Lazy

from .cookie_jar import CookieJarResource, CookiesRefreshResult
from .fetcher import fetch as orchestrate
from .fetcher_response import build_ask_response
from .llm_resource import LlmExtractorResource
from .models import AskResponse, FetchResponse
from .packages.browser_pool import BrowserPool
from .packages.cookie_store.models import ChromeCookieAccessError
from .settings import AppSettings
from .state import AppState


class WebRouter(a2kit.Router):
    """Routes web-fetch tools. CLI surface: `a2web web <tool>`."""

    slug = "web"

    def __init__(self, *, settings: AppSettings | None = None) -> None:
        """Optionally filter `fetch_raw` out of the surface.

        a2kit's `Router.__init__` reads the `tools` tuple from the class
        (not the instance), so when `settings.ask_only` is true we
        rewrite the class attr before delegating up. The router is a
        singleton per app, so class-attr mutation is safe here. Reads
        settings from env when None — convenient for the default
        `app.add_router(WebRouter())` path.
        """
        if settings is None:
            settings = AppSettings()
        if settings.ask_only:
            type(self).tools = (WebRouter.ask,)
        else:
            type(self).tools = (WebRouter.ask, WebRouter.fetch_raw)
        super().__init__()

    @a2kit.read(
        open_world=True,
        title="Ask a Question About a Web Page",
    )
    async def ask(
        self,
        *,
        url: Annotated[str, pydantic.Field(description="Absolute http(s) URL to fetch.")],
        question: Annotated[
            str,
            pydantic.Field(
                min_length=1,
                description=(
                    "What you want to know from this page. The page is fetched, "
                    "then a small fast model (Claude Haiku 4.5 by default) extracts "
                    "a focused answer server-side — keeping your context tiny. "
                    "Phrase it the way you would ask a colleague who just read the "
                    "page: 'What does this article say about X?', 'List the bags "
                    "reviewed with each verdict.', 'Top 3 recommendations and why.'"
                ),
            ),
        ],
        include_links: Annotated[
            bool,
            pydantic.Field(
                description=(
                    "Include the extracted `links` array in the response. Default "
                    "False — links are a large share of payload bytes on aggregator "
                    "pages and most ask-shaped tasks don't need them."
                ),
            ),
        ] = False,
        link_roles: Annotated[
            list[str] | None,
            pydantic.Field(
                description=(
                    "When include_links=True, filter to these DOM roles. Choices: "
                    "'primary' (default), 'nav', 'meta', 'footer'. Pass None for everything."
                ),
            ),
        ] = None,
        debug: Annotated[
            bool,
            pydantic.Field(
                description=(
                    "Return the full `diagnostics` trace plus timing/cache "
                    "metadata. Default False — `diagnostics_summary` is "
                    "populated on failures regardless."
                ),
            ),
        ] = False,
        include_content: Annotated[
            bool,
            pydantic.Field(
                description=(
                    "Also return the full page markdown in `content_md` (plus "
                    "the `headings` index) for grounding. Default False — `ask` "
                    "returns the extracted answer, not the page; the small "
                    "server-side model already read the page for you. Pass True "
                    "only when you need to verify the answer against source."
                ),
            ),
        ] = False,
        wrap_content: Annotated[
            bool,
            pydantic.Field(
                description=("Wrap content_md with HTML-comment markers carrying source URL + 'untrusted content' warning. Default True."),
            ),
        ] = True,
        next_links: Annotated[
            bool,
            pydantic.Field(
                description=(
                    "Return up to 10 curated 'what to fetch next' links in "
                    "`next_links`. Drilldown / related / source candidates "
                    "from the site handler and/or LLM extraction. Default True; "
                    "pass False on terminal fetches where you won't drill down "
                    "to save a few hundred output tokens."
                ),
            ),
        ] = True,
        max_content_chars: Annotated[
            int | None,
            pydantic.Field(
                description=(
                    "Cap on content chars sent to the extractor LLM. Default None "
                    "(uses extractor default of 100000). Lower values cut cost on "
                    "pages dumping JSON state you won't read, but trade quality "
                    "for cost — don't go below ~20000 unless you know the answer "
                    "is in the first viewport."
                ),
            ),
        ] = None,
        include_routing: Annotated[
            bool,
            pydantic.Field(
                description=(
                    "Include the router-shape fields on the response. Default True. "
                    "Router-shape adds seven fields (`structural_form`, `shape`, "
                    "`genre`, `obstacle`, `ask_here`, `try_url`, plus `answer`) "
                    "describing what the page IS and ABOUT, plus same-URL follow-up "
                    "questions and different-URL drilldowns. Same extraction call. "
                    "Opt out for the lean v0.14 envelope or high-volume cost-sensitive "
                    "flows."
                ),
            ),
        ] = True,
        state: AppState,
        browser_pool: Lazy[BrowserPool],
        llm_extractor: Lazy[LlmExtractorResource],
        cookie_jar: Lazy[CookieJarResource],
    ) -> AskResponse:
        """**Primary web-fetch tool. Use this for any question about a web page.**

        Fetches the URL via the adaptive tier cascade (site handlers → raw
        HTTP with TLS impersonation → Jina reader → archive fallback →
        Camoufox browser as last resort), then runs the server-side LLM
        extractor over the content to answer your `question`. Returns the
        focused answer in `extracted_answer`. Pass `include_content=True` to
        also get the page markdown in `content_md` for grounding.

        Prefer this over `fetch_raw` for ~95%% of web reads. The
        extraction model is small and cheap (Haiku 4.5), so server-side
        answers cost a fraction of streaming raw HTML into a larger model.

        When the LLM is unavailable (no API key and no Claude Code OAuth
        session), the fetch still succeeds, `extracted_answer` is None,
        and an operator hint records the reason — callers can fall back
        to reading `content_md` directly.

        Emits typed events on a2kit's LDD channel during the fetch.
        """
        roles_filter = frozenset(link_roles) if link_roles is not None else frozenset({"primary"})
        response = await orchestrate(
            url,
            state=state,
            browser_pool=browser_pool,
            llm_extractor=llm_extractor,
            cookie_jar=cookie_jar,
            include_links=include_links,
            link_roles=roles_filter,
            wrap_content=wrap_content,
            debug=debug,
            ask=question,
            next_links=next_links,
            max_content_chars=max_content_chars,
            include_routing=include_routing,
        )
        return build_ask_response(response, include_content=include_content, debug=debug)

    @a2kit.read(
        open_world=True,
        title="Fetch Raw Web Content (Fallback)",
    )
    async def fetch_raw(
        self,
        *,
        url: Annotated[str, pydantic.Field(description="Absolute http(s) URL to fetch.")],
        include_links: Annotated[
            bool,
            pydantic.Field(
                description=(
                    "Include the extracted `links` array in the response. Default "
                    "False — links are a large share of payload bytes on aggregator pages."
                ),
            ),
        ] = False,
        link_roles: Annotated[
            list[str] | None,
            pydantic.Field(
                description=("When include_links=True, filter to these DOM roles: 'primary' (default), 'nav', 'meta', 'footer'."),
            ),
        ] = None,
        debug: Annotated[
            bool,
            pydantic.Field(
                description="Return the full `diagnostics` trace. Default False.",
            ),
        ] = False,
        wrap_content: Annotated[
            bool,
            pydantic.Field(
                description=("Wrap content_md with HTML-comment markers carrying source URL + 'untrusted content' warning. Default True."),
            ),
        ] = True,
        next_links: Annotated[
            bool,
            pydantic.Field(
                description=(
                    "Return up to 10 curated 'what to fetch next' links in "
                    "`next_links` (drilldown / related / source / discussion). "
                    "Tier-1 site handler candidates work without ask=; default True."
                ),
            ),
        ] = True,
        state: AppState,
        browser_pool: Lazy[BrowserPool],
        cookie_jar: Lazy[CookieJarResource],
    ) -> FetchResponse:
        """**Fallback only — prefer `ask` for ~95%% of web reads.**

        Returns the page's markdown content with no server-side LLM
        extraction. Use only when:

        1. You need the full structural content (link graphs, repeated
           rows for scraping, tables to transform).
        2. A previous `ask` call returned `extracted_answer: null` with
           an `llm_unavailable` operator hint and you need the page text
           to answer your own question.
        3. `ask`'s answer is suspect and you need to verify against
           source.

        Do not default to this tool — `ask` is cheaper end-to-end because
        the server-side Haiku extractor is much smaller than the model
        calling this tool. Same tier cascade, same diagnostics, just
        without the extraction phase.
        """
        roles_filter = frozenset(link_roles) if link_roles is not None else frozenset({"primary"})
        return await orchestrate(
            url,
            state=state,
            browser_pool=browser_pool,
            llm_extractor=None,
            cookie_jar=cookie_jar,
            include_links=include_links,
            link_roles=roles_filter,
            wrap_content=wrap_content,
            debug=debug,
            ask=None,
            next_links=next_links,
        )

    tools: ClassVar[tuple[Callable[..., Any], ...]] = (ask, fetch_raw)


class CookiesRouter(a2kit.Router):
    """Routes cookie-management tools. CLI surface: `a2web cookies <tool>`."""

    slug = "cookies"

    @a2kit.write(
        open_world=False,
        destructive=False,
        idempotent=True,
        title="Refresh Browser Cookies",
    )
    async def refresh(
        self,
        *,
        state: AppState,
        cookie_jar: Lazy[CookieJarResource],
    ) -> CookiesRefreshResult:
        """Mirror the configured browser profile's cookies into a2web's sqlite.

        Reads the user's local Chrome (macOS) or Firefox profile, decrypts
        any encrypted values, and atomically replaces the existing mirror
        for the configured (profile, browser). Subsequent fetches read from
        a2web's own sqlite — Chrome can keep running and no Keychain prompts
        happen until the next refresh.

        Settings: `cookie_source` selects the browser, `cookie_profile`
        selects the profile name. With `cookie_source="none"` (the default)
        this tool returns zero count and an explanatory note — no DB or
        Keychain access happens.
        """
        s = state.settings
        if s.cookie_source == "none":
            from datetime import UTC, datetime

            return CookiesRefreshResult(
                profile=s.cookie_profile,
                browser="none",
                refreshed_count=0,
                refreshed_at=datetime.now(UTC),
                notes=(
                    "cookie_source is 'none' — set A2WEB_COOKIE_SOURCE=chrome (or "
                    "firefox) to enable. No DB or Keychain access was performed."
                ),
            )
        jar = await cookie_jar()
        try:
            result = await jar.refresh()
        except ChromeCookieAccessError as exc:
            from datetime import UTC, datetime

            return CookiesRefreshResult(
                profile=s.cookie_profile,
                browser=str(s.cookie_source),
                refreshed_count=0,
                refreshed_at=datetime.now(UTC),
                notes=f"refresh failed: {exc}",
            )
        return CookiesRefreshResult(
            profile=result.profile,
            browser=result.browser,
            refreshed_count=result.refreshed_count,
            refreshed_at=result.refreshed_at,
            notes="",
        )

    tools: ClassVar[tuple[Callable[..., Any], ...]] = (refresh,)
