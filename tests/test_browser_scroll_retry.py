"""Browser tier scroll-on-thin retry — unit tests.

Covers openspec/changes/harsh-test-session-fixes/specs/browser-tier/spec.md
(scroll subset).
"""

from __future__ import annotations

import pytest

from a2web.tiers.browser import _host_is_js_heavy, _scroll_and_retry


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


def test_host_is_js_heavy_recognizes_seed_hosts() -> None:
    """No-state path: just the seed list (no AppSettings extras)."""

    class _S:
        settings = None

    assert _host_is_js_heavy("https://x.com/elonmusk", _S()) is True
    assert _host_is_js_heavy("https://www.trendyol.com/sr", _S()) is True  # www. stripped
    assert _host_is_js_heavy("https://trendyol.com/sr", _S()) is True
    assert _host_is_js_heavy("https://news.ycombinator.com/", _S()) is False
    assert _host_is_js_heavy("", _S()) is False
