"""Browser tier — Camoufox-rendered fetch for JS-required pages.

Out-of-band tier: registered but NOT in `TIER_ORDER`. The orchestrator
dispatches it only when the gate sets `suggested_tier == "browser"`.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import a2kit
import a2kit.ldd
import trafilatura

from ..events import StageEnded, StageStarted
from ..models import OperatorHint, Verdict

if TYPE_CHECKING:
    from ..cookie_jar import Cookie
    from ..packages.browser_pool import BrowserPool
    from ..state import AppState
    from . import TierResult


def _cookie_to_playwright(cookie: Cookie) -> dict[str, Any]:
    """Convert a domain Cookie to Playwright's `add_cookies` shape.

    - `host_key` → `domain`
    - `expires_utc` (None for session) → `expires` (-1 for session)
    - `is_secure` / `is_httponly` (int 0/1) → bool
    - `samesite` lowercase → titlecase enum; None omitted
    """
    out: dict[str, Any] = {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.host_key,
        "path": cookie.path,
        "expires": cookie.expires_utc if cookie.expires_utc is not None else -1,
        "secure": bool(cookie.is_secure),
        "httpOnly": bool(cookie.is_httponly),
    }
    if cookie.samesite is not None:
        out["sameSite"] = cookie.samesite.capitalize()
    return out


_FIX_HINT = "python -m playwright install firefox && python -m camoufox fetch"


def _to_markdown(html: str, url: str) -> str:
    md = trafilatura.extract(html, url=url, output_format="markdown", include_comments=False, include_tables=True)
    return md or ""


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


async def _scroll_and_retry(page: Any, original_html: str) -> str:
    """Scroll-to-bottom + 2s networkidle wait + re-snapshot.

    Returns whichever capture (original or post-scroll) is longer. Never
    raises — timeout or page-eval errors fall back to the original. Emits
    `browser_scroll_retry` LDD events so operators can measure firing rate.
    """
    t_ms = 0  # relative — caller manages the absolute clock
    await a2kit.ldd.event(StageStarted(t_ms=t_ms, step="browser_scroll_retry"))
    start = time.perf_counter()
    larger = original_html
    outcome = "smaller"
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            await page.wait_for_load_state("networkidle", timeout=2_000)
        except Exception:
            # networkidle never settled — try a brief sleep then snapshot anyway
            await asyncio.sleep(0.5)
        retry_html = await page.content()
        if len(retry_html) > len(original_html):
            larger = retry_html
            outcome = "larger"
    except Exception:
        outcome = "timeout"
    dur_ms = int((time.perf_counter() - start) * 1000)
    await a2kit.ldd.event(StageEnded(t_ms=t_ms, step="browser_scroll_retry", verdict=Verdict.ok, dur_ms=dur_ms, extra={"outcome": outcome}))
    return larger


def _unavailable_result(url: str, message: str) -> TierResult:
    from . import TierResult  # local - circular with package init

    return TierResult(
        body=b"",
        content_type="text/html",
        status_code=0,
        final_url=url,
        from_browser=True,
        operator_hint=OperatorHint(code="browser_unavailable", message=message, fix=_FIX_HINT),
        verdict=Verdict.connection_error,
    )


class BrowserTier:
    """Camoufox-rendered fetch. Out-of-band - gate-dispatched only."""

    name: str = "browser"

    async def fetch(
        self,
        url: str,
        *,
        state: AppState,
        pool: BrowserPool | None = None,
        proxy_url: str | None = None,
        conditional_extras: dict[str, str] | None = None,
        cookies_full: list[Cookie] | None = None,
        **kwargs: Any,
    ) -> TierResult:
        del proxy_url, conditional_extras, kwargs  # Browser tier ignores all today.
        from . import Rendered, TierResult  # local - circular with package init

        if not state.settings.browser_enabled:
            return _unavailable_result(url, "browser tier disabled (A2WEB_BROWSER_ENABLED=false)")
        if pool is None:
            return _unavailable_result(url, "browser tier not provisioned (no BrowserPool injected)")

        try:
            await pool._ensure()
        except ImportError as exc:
            return _unavailable_result(url, f"camoufox not installed: {exc}")
        except Exception as exc:  # browser launch failed
            return _unavailable_result(url, f"browser launch failed: {exc}")

        budget_s = float(state.settings.browser_page_budget_s)
        wall_start = time.perf_counter()
        try:
            async with pool.acquire(url) as page:
                if cookies_full:
                    # Seed cookies on the BrowserContext BEFORE navigation so
                    # the request goes out logged-in. add_cookies upserts by
                    # (name, domain, path) — refreshed values override any
                    # warm context state.
                    await page.context.add_cookies(
                        [_cookie_to_playwright(c) for c in cookies_full],
                    )
                try:
                    response = await asyncio.wait_for(
                        page.goto(url, wait_until="networkidle"),
                        timeout=budget_s,
                    )
                except TimeoutError:
                    wall_ms = int((time.perf_counter() - wall_start) * 1000)
                    return TierResult(
                        body=b"",
                        content_type="text/html",
                        status_code=0,
                        final_url=url,
                        from_browser=True,
                        js_executed=True,
                        browser_wall_ms=wall_ms,
                        verdict=Verdict.timeout,
                    )

                status_code = response.status if response is not None else 200
                final_url = page.url or url
                html = await page.content()
                # v0.10 (harsh-test-session-fixes): scroll-on-thin retry.
                # When the first snapshot is sub-4KB and the host is in the
                # JS_HEAVY_HOSTS set, scroll to the bottom + wait 2s for
                # virtualized/lazy-loaded grids (Trendyol pattern). Keep the
                # larger of the two snapshots.
                if len(html) < 4_096 and _host_is_js_heavy(final_url, state):
                    larger = await _scroll_and_retry(page, html)
                    html = larger
        except Exception as exc:  # navigation/network errors
            del exc  # error string was unused upstream
            wall_ms = int((time.perf_counter() - wall_start) * 1000)
            return TierResult(
                body=b"",
                content_type="text/html",
                status_code=0,
                final_url=url,
                from_browser=True,
                js_executed=True,
                browser_wall_ms=wall_ms,
                verdict=Verdict.connection_error,
            )

        wall_ms = int((time.perf_counter() - wall_start) * 1000)
        markdown = await asyncio.to_thread(_to_markdown, html, final_url)

        verdict = Verdict.ok if markdown else Verdict.length_floor
        return TierResult(
            body=html.encode("utf-8"),
            content_type="text/html",
            status_code=status_code,
            final_url=final_url,
            from_browser=True,
            js_executed=True,
            browser_wall_ms=wall_ms,
            browser_bytes=len(html),
            pre_rendered=Rendered(content_md=markdown),
            verdict=verdict,
        )
