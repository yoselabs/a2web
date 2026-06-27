"""ZendriverBackend — a CDP rendering engine behind the `BrowserBackend` seam.

TRANSIENT (browser-backend-bakeoff): the bake-off's CDP candidate, and the
proof the interface spans engine *families*, not just the Playwright API.
zendriver drives Chromium directly over CDP (its own `Browser`/`Tab` objects,
no Playwright `Page`), so unlike Patchright/rebrowser it can't be a
`PlaywrightBackend` launch_fn — it implements `render(...)` itself and shapes
CDP navigation / content / cookies into the same domain-free `RenderedPage`.

v1 (design D3 + open question): **per-render browser launch**, no host pool —
the simplest correct shape, perfect per-render isolation. The speed axis of the
bake-off decides whether a shared-browser pool is worth adding; if zendriver
loses only on speed, that's the optimization to try before discarding it.

Domain-free: only `RenderedPage` crosses the boundary — never a `Tab`, CDP
session, or domain type. Reuses the engine-neutral helpers from `playwright.py`
(that module survives the bake-off regardless of winner — gated Camoufox keeps
it), so the one-line summary + thin-floor heuristic stay identical across
engines and the bake-off compares engines, not helper drift.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any

from .base import BackendCookie, RenderedPage, RenderOutcome
from .playwright import _THIN_FLOOR, _ms, _summarize_exc

_SAMESITE = {"strict": "STRICT", "lax": "LAX", "none": "NONE"}


def _cookie_to_cdp(cookie: BackendCookie, cdp: Any) -> Any:
    """Engine-neutral `BackendCookie` → CDP `Network.CookieParam`."""
    same_site = None
    if cookie.samesite is not None:
        enum_name = _SAMESITE.get(cookie.samesite.lower())
        if enum_name is not None:
            same_site = getattr(cdp.network.CookieSameSite, enum_name)
    return cdp.network.CookieParam(
        name=cookie.name,
        value=cookie.value,
        domain=cookie.domain,
        path=cookie.path,
        expires=cookie.expires,
        secure=cookie.secure,
        http_only=cookie.http_only,
        same_site=same_site,
    )


async def _scroll_and_retry_cdp(tab: Any, original_html: str) -> str:
    """Scroll-to-bottom + brief settle + re-snapshot; keep the larger capture.

    The CDP-side mirror of `playwright._scroll_and_retry` — same intent (a
    sub-floor first paint on a JS-heavy host often grows after scroll), zendriver
    methods. Never raises.
    """
    larger = original_html
    with suppress(Exception):
        for _ in range(4):
            await tab.scroll_down(150)
        await asyncio.sleep(2.0)
        retry_html = await tab.get_content()
        if len(retry_html) > len(original_html):
            larger = retry_html
    return larger


class ZendriverBackend:
    """CDP rendering engine. Per-render launch (v1). Satisfies `BrowserBackend`."""

    def __init__(self, *, name: str = "zendriver", page_budget_s: int = 30) -> None:
        self.name = name
        self.page_budget_s = page_budget_s

    async def render(
        self,
        url: str,
        *,
        cookies: list[BackendCookie],
        budget_s: float,
        js_heavy: bool,
    ) -> RenderedPage:
        try:
            import zendriver as zd
        except ImportError as exc:
            return RenderedPage(outcome=RenderOutcome.unavailable, final_url=url, detail=f"engine not installed: {exc}")

        wall_start = time.perf_counter()
        browser: Any | None = None
        try:
            try:
                # zendriver's default connection handshake (0.25s x 10 tries
                # ~2.5s) gives up before Chromium's CDP socket is ready on a
                # cold/loaded host — the browser launches fine, the connect just
                # races it. Widen the window (1s x 15 ~15s headroom); it returns
                # as soon as the socket answers, so the common path stays fast.
                config = zd.Config(headless=True)
                config.browser_connection_timeout = 1.0
                config.browser_connection_max_tries = 15
                browser = await zd.start(config=config)
            except Exception as exc:  # launch failed (no binary, sandbox, etc.)
                return RenderedPage(outcome=RenderOutcome.unavailable, final_url=url, detail=f"browser launch failed: {exc}")

            if cookies:
                # Seed cookies on the browser jar BEFORE navigation so the
                # request goes out logged-in (parity with the Playwright path).
                await browser.cookies.set_all([_cookie_to_cdp(c, zd.cdp) for c in cookies])

            try:
                html, final_url = await asyncio.wait_for(
                    self._navigate(browser, url, js_heavy),
                    timeout=budget_s,
                )
            except TimeoutError:
                return RenderedPage(outcome=RenderOutcome.timeout, final_url=url, js_executed=True, wall_ms=_ms(wall_start))
        except Exception as exc:  # navigation / CDP / driver errors
            return RenderedPage(
                outcome=RenderOutcome.error,
                final_url=url,
                js_executed=True,
                wall_ms=_ms(wall_start),
                detail=_summarize_exc(exc),
            )
        finally:
            if browser is not None:
                with suppress(Exception):
                    await browser.stop()

        return RenderedPage(
            outcome=RenderOutcome.ok,
            html=html,
            final_url=final_url,
            # CDP doesn't surface the main-frame nav status as cheaply as
            # Playwright's response object; v1 reports 200 on a successful
            # content capture and leans on content-side block detection. If
            # zendriver wins, capture it via a Network.responseReceived handler.
            status_code=200,
            js_executed=True,
            wall_ms=_ms(wall_start),
            bytes_transferred=len(html),
        )

    async def _navigate(self, browser: Any, url: str, js_heavy: bool) -> tuple[str, str]:
        tab = await browser.get(url)
        await tab.wait_for_ready_state("complete", timeout=int(self.page_budget_s))
        html = await tab.get_content()
        if len(html) < _THIN_FLOOR and js_heavy:
            html = await _scroll_and_retry_cdp(tab, html)
        return html, tab.url or url

    async def __aenter__(self) -> ZendriverBackend:
        # Per-render launch (v1) — nothing persistent to enter.
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        # No persistent browser to unwind; each render owns its own lifecycle.
        return None
