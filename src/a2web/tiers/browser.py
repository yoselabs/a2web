"""Browser tier — JS-capable rendered fetch, engine-agnostic.

Delegates rendering to the selected `BrowserBackend` (`patchright` fast rung,
`zendriver` robust rung — Camoufox is gated off, see
`_manifests/browser_backends/camoufox.py`) and owns only the engine-agnostic
tail: trafilatura → markdown, the `RenderOutcome` → `Verdict`/`OperatorHint`
mapping, and `TierResult` assembly. No Playwright type or `BrowserPool`
appears here.

Out-of-band tier: registered but NOT in `TIER_ORDER`. The orchestrator
dispatches it only when the gate sets `suggested_tier == "browser"`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from any_browser import BackendCookie, RenderOutcome
from content_extract import ExtractedContent, extract_markdown

from ..models import (
    Heading,
    Link,
    Verdict,
    browser_internal_error_hint,
    browser_unavailable_hint,
)
from ..packages.block_detector import LENGTH_FLOOR

if TYPE_CHECKING:
    from any_browser import BrowserBackend, RenderedPage

    from ..cookie_jar import Cookie
    from ..state import AppState
    from . import TierResult


# The two browser-tier remediation strings moved to `models.py` alongside their
# factories (`browser_unavailable_hint` / `browser_internal_error_hint`), so
# every operator-hint string in a2web has exactly one home.


def _cookie_to_backend(cookie: Cookie) -> BackendCookie:
    """Domain `Cookie` → engine-neutral `BackendCookie`."""
    return BackendCookie(
        name=cookie.name,
        value=cookie.value,
        domain=cookie.host_key,
        path=cookie.path,
        expires=float(cookie.expires_utc) if cookie.expires_utc is not None else None,
        secure=bool(cookie.is_secure),
        http_only=bool(cookie.is_httponly),
        samesite=cookie.samesite,
    )


async def _extract(html: str, url: str) -> ExtractedContent:
    """Canonical extraction — markdown AND links AND headings, one off-thread parse.

    NOT a bare `trafilatura.extract`. That returns markdown only, and using it
    here silently discarded every anchor on the page, which is what made
    `other_pages` impossible to emit on any browser-served page for two and a
    half months (`eval/findings_2026-07-28.md`). Pinned by
    `tests/architecture/test_trafilatura_funnel.py`.

    `include_links` is deliberately NOT set. Measured 2026-07-28: the flag
    changes only how `content_md` RENDERS — the structured `links` list is
    returned either way — and turning it on destroys list structure (a 3-bullet
    listing rendered as 0 bullets with items run together). The digest needs the
    structured links; the model reads the markdown. Taking both from one
    default-flag parse costs nothing and keeps the body readable.
    """
    return await extract_markdown(html, url)


def _upstream_error_verdict(status: int) -> Verdict:
    """Map a rendered UPSTREAM error status to a domain Verdict (tier-truthfulness).

    404 → `not_found` so a browser-confirmed dead URL corroborates the raw tier;
    401/403 → `paywall` (mirrors the jina unwrap so a walled surface keeps its
    archive routing); everything else → `connection_error`.
    """
    if status == 404:
        return Verdict.not_found
    if status in (401, 403):
        return Verdict.paywall
    return Verdict.connection_error


def _host_is_js_heavy(url: str, state: AppState | None) -> bool:
    """Return True if the URL's host is in the JS_HEAVY_HOSTS set.

    Imports `js_heavy_hosts` lazily to avoid the tier-→-fetcher import cycle
    that direct top-level imports would create.
    """
    if not url:
        return False
    from ..fetcher import js_heavy_hosts

    settings = state.settings if (state is not None and hasattr(state, "settings")) else None
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host in js_heavy_hosts(settings)


def _unavailable_result(url: str, message: str) -> TierResult:
    from . import TierResult  # local - circular with package init

    return TierResult(
        body=b"",
        content_type="text/html",
        status_code=0,
        final_url=url,
        from_browser=True,
        operator_hint=browser_unavailable_hint(message),
        verdict=Verdict.connection_error,
    )


class BrowserTier:
    """JS-capable rendered fetch. Out-of-band - gate-dispatched only.

    Engine-agnostic: the backend is injected per `fetch`. The same class backs
    both browser rungs — `browser` (fast) and `browser_robust` (CDP) — which
    differ only by `name` (for the decision log) and the backend the
    orchestrator hands them.
    """

    def __init__(self, *, name: str = "browser") -> None:
        self.name = name

    async def fetch(
        self,
        url: str,
        *,
        state: AppState,
        backend: BrowserBackend | None = None,
        proxy_url: str | None = None,
        conditional_extras: dict[str, str] | None = None,
        cookies_full: list[Cookie] | None = None,
        scroll: bool = False,
        **kwargs: Any,
    ) -> TierResult:
        del proxy_url, conditional_extras, kwargs  # Browser tier ignores the rest today.
        from . import Rendered, TierResult  # local - circular with package init

        if not state.settings.browser_enabled:
            return _unavailable_result(url, "browser tier disabled (A2WEB_BROWSER_ENABLED=false)")
        if backend is None:
            return _unavailable_result(url, "browser tier not provisioned (no backend injected)")

        cookies = [_cookie_to_backend(c) for c in cookies_full] if cookies_full else []
        budget_s = float(state.settings.browser_page_budget_s)
        js_heavy = _host_is_js_heavy(url, state)

        # `scroll` (listing-completeness Slice 2b) asks the backend to scroll an
        # infinite-scroll listing to completion before snapshotting.
        page: RenderedPage = await backend.render(url, cookies=cookies, budget_s=budget_s, js_heavy=js_heavy, scroll_to_stable=scroll)

        if page.outcome is RenderOutcome.unavailable:
            return _unavailable_result(url, page.detail or "browser engine unavailable")
        if page.outcome is RenderOutcome.timeout:
            return TierResult(
                body=b"",
                content_type="text/html",
                status_code=0,
                final_url=page.final_url or url,
                from_browser=True,
                js_executed=page.js_executed,
                browser_wall_ms=page.wall_ms,
                verdict=Verdict.timeout,
            )
        if page.outcome is RenderOutcome.error:
            # Don't swallow the cause: surface it as a structured hint so the
            # agent/operator sees *why* the browser tier produced nothing.
            return TierResult(
                body=b"",
                content_type="text/html",
                status_code=0,
                final_url=page.final_url or url,
                from_browser=True,
                js_executed=page.js_executed,
                browser_wall_ms=page.wall_ms,
                operator_hint=browser_internal_error_hint(page.detail),
                verdict=Verdict.connection_error,
            )

        # outcome == ok — run trafilatura over the rendered HTML.
        extracted = await _extract(page.html, page.final_url)
        markdown = extracted.content_md
        # Tier-truthfulness: a rendered UPSTREAM error page (4xx/5xx) with only a
        # thin body is a real error, not content — surface the status so a
        # browser-confirmed 404 is an observation in the decision log, not a
        # buried diagnostic. Substantial content on an error status is treated as
        # soft-404-defeated (real content behind a scraper-shedding status) and
        # returned as `ok`. The floor is the same thin/real discriminator the gate uses.
        if page.status_code >= 400 and len(markdown) < LENGTH_FLOOR:
            verdict = _upstream_error_verdict(page.status_code)
        else:
            verdict = Verdict.ok if markdown else Verdict.length_floor
        return TierResult(
            body=page.html.encode("utf-8"),
            content_type="text/html",
            status_code=page.status_code,
            final_url=page.final_url,
            from_browser=True,
            js_executed=page.js_executed,
            browser_wall_ms=page.wall_ms,
            browser_bytes=page.bytes_transferred,
            subresource_blocks=page.subresource_blocks,
            pre_rendered=Rendered(
                content_md=markdown,
                title=extracted.title,
                byline=extracted.byline,
                headings=[Heading(level=h.level, text=h.text) for h in extracted.headings],
                links=[Link(anchor=lk.anchor, href=lk.href, role=lk.role) for lk in extracted.links],
            ),
            verdict=verdict,
        )
