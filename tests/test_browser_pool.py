"""BrowserPool — per-host context reuse, LRU eviction, idle eviction.

Tests use a stub Camoufox/Browser (no Firefox launched). Real-binary
integration tests live behind @pytest.mark.browser.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from a2web.packages.browser_pool import BrowserPool


class _StubPage:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _StubContext:
    def __init__(self) -> None:
        self.closed = False
        self.pages: list[_StubPage] = []

    async def new_page(self) -> _StubPage:
        page = _StubPage()
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True


class _StubBrowser:
    def __init__(self) -> None:
        self.contexts: list[_StubContext] = []

    async def new_context(self) -> _StubContext:
        ctx = _StubContext()
        self.contexts.append(ctx)
        return ctx


class _StubCamoufox:
    def __init__(self, headless: bool = True) -> None:
        self.browser = _StubBrowser()
        self.exited = False

    async def __aenter__(self) -> _StubBrowser:
        return self.browser

    async def __aexit__(self, *exc: Any) -> None:
        self.exited = True


def _patch_camoufox(monkeypatch: pytest.MonkeyPatch) -> _StubCamoufox:
    """Replace AsyncCamoufox import inside pool.start()."""
    import sys
    import types

    stub_module = types.ModuleType("camoufox.async_api")
    holder: dict[str, _StubCamoufox] = {}

    def _factory(headless: bool = True) -> _StubCamoufox:
        cf = _StubCamoufox(headless=headless)
        holder["cf"] = cf
        return cf

    stub_module.AsyncCamoufox = _factory  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "camoufox.async_api", stub_module)
    monkeypatch.setitem(sys.modules, "camoufox", types.ModuleType("camoufox"))
    return holder  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_start_initializes_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _patch_camoufox(monkeypatch)
    pool = BrowserPool()
    await pool.start()
    assert "cf" in holder
    await pool.close()
    assert holder["cf"].exited is True


@pytest.mark.asyncio
async def test_same_host_reuses_context(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _patch_camoufox(monkeypatch)
    pool = BrowserPool()
    await pool.start()
    try:
        async with pool.acquire("https://example.com/a") as page1:
            assert page1 is not None
        async with pool.acquire("https://example.com/b") as page2:
            assert page2 is not None
        # Both pages came from the same context (cookie jar warm).
        assert len(holder["cf"].browser.contexts) == 1
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_lru_evicts_oldest_at_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _patch_camoufox(monkeypatch)
    pool = BrowserPool(max_pool=2)
    await pool.start()
    try:
        async with pool.acquire("https://a.example/"):
            pass
        async with pool.acquire("https://b.example/"):
            pass
        # 5th host arrival evicts a.example (LRU).
        async with pool.acquire("https://c.example/"):
            pass
        # 3 contexts created, but the first should be closed.
        assert len(holder["cf"].browser.contexts) == 3
        assert holder["cf"].browser.contexts[0].closed is True
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_idle_eviction(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _patch_camoufox(monkeypatch)
    pool = BrowserPool(idle_timeout_s=0)  # everything is immediately stale
    await pool.start()
    try:
        async with pool.acquire("https://a.example/"):
            pass
        # Force last_used into the past.
        for ctx in pool._contexts.values():
            ctx.last_used = time.monotonic() - 9999.0
        async with pool.acquire("https://b.example/"):
            pass
        # Yield once so eviction-task fires.
        await asyncio.sleep(0)
        # Stale a.example was evicted; b.example remains.
        # (the context for a was closed)
        assert any(c.closed for c in holder["cf"].browser.contexts)
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_close_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_camoufox(monkeypatch)
    pool = BrowserPool()
    await pool.start()
    await pool.close()
    await pool.close()  # second close is a no-op


@pytest.mark.asyncio
async def test_acquire_before_start_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_camoufox(monkeypatch)
    pool = BrowserPool()
    with pytest.raises(RuntimeError, match="not called"):
        async with pool.acquire("https://example.com/"):
            pass
