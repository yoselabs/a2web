"""Browser tier scroll-on-thin retry — unit tests.

Covers openspec/changes/harsh-test-session-fixes/specs/browser-tier/spec.md
(scroll subset).
"""

from __future__ import annotations

from typing import Any

import pytest

from a2web.packages.browser_backends.base import BackendCookie, RenderedPage, RenderOutcome
from a2web.packages.browser_backends.playwright import _scroll_and_retry, _scroll_to_stable
from a2web.tiers.browser import _host_is_js_heavy


class _FakePage:
    """Records evaluate calls; returns a configured post-scroll HTML."""

    def __init__(self, *, post_scroll_html: str, raise_on_eval: bool = False) -> None:
        self._post = post_scroll_html
        self._raise = raise_on_eval
        self.evaluated: list[str] = []
        self.waited: int = 0

    async def evaluate(self, expr: str) -> None:
        self.evaluated.append(expr)
        if self._raise:
            raise RuntimeError("page crashed mid-eval")

    async def wait_for_load_state(self, state: str, **kwargs: int) -> None:
        del kwargs
        self.waited += 1

    async def content(self) -> str:
        return self._post


@pytest.mark.asyncio
async def test_scroll_retry_returns_larger_capture() -> None:
    """Post-scroll HTML is longer → returned as the winning capture."""
    original = "<html>thin</html>"
    rich = "<html>" + "x" * 20_000 + "</html>"
    page = _FakePage(post_scroll_html=rich)
    result = await _scroll_and_retry(page, original)
    assert result == rich
    assert page.evaluated == ["window.scrollTo(0, document.body.scrollHeight)"]


@pytest.mark.asyncio
async def test_scroll_retry_keeps_original_when_smaller() -> None:
    """Post-scroll HTML is shorter (X served same noscript stub) → original kept."""
    original = "<html>" + "x" * 5_000 + "</html>"
    page = _FakePage(post_scroll_html="<html>tiny</html>")
    result = await _scroll_and_retry(page, original)
    assert result == original


@pytest.mark.asyncio
async def test_scroll_retry_swallows_page_exception() -> None:
    """page.evaluate raising must not propagate; falls back to original."""
    original = "<html>thin</html>"
    page = _FakePage(post_scroll_html="never returned", raise_on_eval=True)
    result = await _scroll_and_retry(page, original)
    assert result == original


class _GrowingPage:
    """Fake page whose `content()` returns successively larger HTML per call.

    Models an infinite-scroll listing that materialises more rows on each
    scroll until it stabilises (the size sequence flattens).
    """

    def __init__(self, sizes: list[int], *, raise_on_eval: bool = False) -> None:
        self._sizes = sizes
        self._i = 0
        self._raise = raise_on_eval
        self.scrolls = 0

    async def evaluate(self, expr: str) -> None:
        del expr
        self.scrolls += 1
        if self._raise:
            raise RuntimeError("page crashed mid-eval")

    async def wait_for_load_state(self, state: str, **kwargs: int) -> None:
        del state, kwargs

    async def content(self) -> str:
        size = self._sizes[min(self._i, len(self._sizes) - 1)]
        self._i += 1
        return "<html>" + ("x" * size) + "</html>"


@pytest.mark.asyncio
async def test_scroll_to_stable_loops_until_growth_stops() -> None:
    # 100 → 200 → 300 → 300: grows for three passes then flattens.
    page = _GrowingPage([100, 200, 300, 300])
    result = await _scroll_to_stable(page, "<html>seed</html>")
    assert result.count("x") == 300  # the largest capture wins
    # Scrolled through the three growth passes plus the one that confirmed stable.
    assert page.scrolls == 4


@pytest.mark.asyncio
async def test_scroll_to_stable_respects_max_passes() -> None:
    # Always-growing (never stabilises) → the pass cap is the safety bound.
    page = _GrowingPage([100, 200, 300, 400, 500, 600, 700, 800, 900, 1000])
    result = await _scroll_to_stable(page, "<html>seed</html>", max_passes=3)
    assert page.scrolls == 3
    assert result.count("x") == 300  # stopped after 3 passes


@pytest.mark.asyncio
async def test_scroll_to_stable_swallows_exception() -> None:
    page = _GrowingPage([100], raise_on_eval=True)
    result = await _scroll_to_stable(page, "<html>seed</html>")
    assert result == "<html>seed</html>"  # first-pass failure → original kept


class _RecordingBackend:
    """Stub `BrowserBackend` that records the `scroll_to_stable` flag it saw."""

    name = "stub"

    def __init__(self) -> None:
        self.scroll_seen: bool | None = None

    async def render(
        self,
        url: str,
        *,
        cookies: list[BackendCookie],
        budget_s: float,
        js_heavy: bool,
        scroll_to_stable: bool = False,
        **_: Any,
    ) -> RenderedPage:
        del cookies, budget_s, js_heavy
        self.scroll_seen = scroll_to_stable
        return RenderedPage(outcome=RenderOutcome.ok, html="<html><body>ok</body></html>", final_url=url, status_code=200, js_executed=True)

    async def __aenter__(self) -> _RecordingBackend:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.mark.asyncio
async def test_browser_tier_threads_scroll_to_backend() -> None:
    from a2web.tiers.browser import BrowserTier
    from tests.conftest import make_default_state

    backend = _RecordingBackend()
    state = make_default_state()
    result = await BrowserTier().fetch("https://shop.example/ara?q=x", state=state, backend=backend, scroll=True)
    assert backend.scroll_seen is True
    assert result.verdict.value == "ok"


def test_host_is_js_heavy_recognizes_seed_hosts() -> None:
    """No-state path: just the seed list (no AppSettings extras)."""

    class _S:
        settings = None

    assert _host_is_js_heavy("https://x.com/elonmusk", _S()) is True
    assert _host_is_js_heavy("https://www.trendyol.com/sr", _S()) is True  # www. stripped
    assert _host_is_js_heavy("https://trendyol.com/sr", _S()) is True
    assert _host_is_js_heavy("https://news.ycombinator.com/", _S()) is False
    assert _host_is_js_heavy("", _S()) is False
