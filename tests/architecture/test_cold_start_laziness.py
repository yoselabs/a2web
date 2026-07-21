"""Cold start: a cheap `query` must construct neither a browser nor an LLM.

**Why this test exists at all.** Under a2kit, laziness was a property of the
framework: a `Lazy[T]` parameter was resolved by the container only if the tool
body awaited it, and nothing else could accidentally resolve it. Hand-wiring
moved that guarantee into a convention — `routers.py` passes
`components.browser_backend` *without* awaiting it, and nothing structurally
stops a future edit from adding `await components.browser_backend()` at the top
of `query` and silently doubling cold start for every caller.

The design named this as the honest risk of the sunset and named this test as
its mitigation. It is the spike's R1 assertion, promoted.

It asserts on **construction**, not on entry: the factory itself is the probe,
so the test fails even if a resource is built and never entered.
"""

from __future__ import annotations

import dataclasses

import pytest

from a2web.components import build_components
from a2web.lazy import lazy
from a2web.packages.browser_backends import BrowserBackend
from a2web.tiers import REGISTRY, TierResult
from tests._helpers.mcp import mcp_client

_BODY = b"<html><body><main>" + b"<p>Adaptive web fetching keeps context small.</p>" * 30 + b"</main></body></html>"


class _RawStub:
    """A raw tier that always wins, so no escalation is ever warranted."""

    name = "raw"

    async def fetch(self, url: str, **kwargs: object) -> TierResult:
        del url, kwargs
        return TierResult(body=_BODY, content_type="text/html", status_code=200, final_url="https://example.org/x")


@pytest.mark.asyncio
async def test_cheap_query_resolves_neither_browser_nor_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "raw", _RawStub())
    built: list[str] = []

    def _browser(_settings: object) -> BrowserBackend:
        built.append("browser")
        raise AssertionError("cold start built a browser backend")

    def _provider(_settings: object) -> object:
        built.append("provider")
        raise AssertionError("cold start built an LLM provider")

    parts = build_components(browser_factory=_browser, browser_robust_factory=_browser, provider_factory=_provider)

    async with mcp_client(components=parts) as client:
        result = await client.call_tool("fetch_raw", {"url": "https://example.org/x"})

    assert result.is_error is False
    assert built == [], f"cold start constructed: {built}"


@pytest.mark.asyncio
async def test_thunks_are_still_wired_when_something_does_await_them() -> None:
    """The companion assertion — laziness that is actually breakage passes the
    test above trivially. A thunk handed a real value must still resolve."""
    sentinel = object()
    parts = dataclasses.replace(build_components(), browser_backend=lazy(sentinel))
    assert await parts.browser_backend() is sentinel
