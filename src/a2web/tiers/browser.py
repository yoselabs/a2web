"""Browser tier - Camoufox-rendered HTML for JS-gated sites.

Out-of-band tier: registered but NOT in `TIER_ORDER`. The orchestrator
dispatches it only when the gate sets `suggested_tier == "browser"`
(Anubis, Turnstile, Akamai BMP, JS-required SPA shells).

Cost: 2-4s cold-start, 1-3s warm. Never invoked on the happy path.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import trafilatura

from ..models import Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


def _to_markdown(html: str, url: str) -> str:
    md = trafilatura.extract(html, url=url, output_format="markdown", include_comments=False, include_tables=True)
    return md or ""


def _unavailable_result(url: str, message: str) -> TierResult:
    from . import TierResult  # local - circular with package init

    return TierResult(
        body=b"",
        content_type="text/html",
        status_code=0,
        final_url=url,
        tier_extras={
            "from_browser": True,
            "operator_hint": {
                "code": "browser_unavailable",
                "message": message,
                "fix": "pip install a2web[browser] && playwright install firefox && camoufox fetch",
            },
        },
        verdict=Verdict.connection_error,
    )


class BrowserTier:
    """Camoufox-rendered fetch. Out-of-band - gate-dispatched only."""

    name: str = "browser"

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        from ..state import ensure_browser_pool
        from . import TierResult  # local - circular with package init

        if not state.settings.browser_enabled:
            return _unavailable_result(url, "browser tier disabled (A2WEB_BROWSER_ENABLED=false)")

        try:
            pool = await ensure_browser_pool(state)
        except ImportError as exc:
            return _unavailable_result(url, f"camoufox not installed: {exc}")
        except Exception as exc:  # browser launch failed
            return _unavailable_result(url, f"browser launch failed: {exc}")

        budget_s = float(state.settings.browser_page_budget_s)
        wall_start = time.perf_counter()
        try:
            async with pool.acquire(url) as page:
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
                        tier_extras={
                            "from_browser": True,
                            "js_executed": True,
                            "browser_wall_ms": wall_ms,
                        },
                        verdict=Verdict.timeout,
                    )

                status_code = response.status if response is not None else 200
                final_url = page.url or url
                html = await page.content()
        except Exception as exc:  # navigation/network errors
            wall_ms = int((time.perf_counter() - wall_start) * 1000)
            return TierResult(
                body=b"",
                content_type="text/html",
                status_code=0,
                final_url=url,
                tier_extras={
                    "from_browser": True,
                    "js_executed": True,
                    "browser_wall_ms": wall_ms,
                    "error": str(exc),
                },
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
            tier_extras={
                "from_browser": True,
                "js_executed": True,
                "browser_wall_ms": wall_ms,
                "browser_bytes": len(html),
                "pre_rendered": {
                    "content_md": markdown,
                    "title": None,
                    "byline": None,
                    "headings": [],
                },
            },
            verdict=verdict,
        )
