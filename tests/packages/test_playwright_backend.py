"""PlaywrightBackend — per-host context reuse, LRU/idle eviction, render outcomes.

Tests use a fake launcher (no Camoufox/Firefox). Real-binary coverage lives
behind the `browser` marker (`tests/.../test_browser_smoke.py`).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from a2web.packages.browser_backends import PlaywrightBackend, RenderOutcome


class _Resp:
    status = 200


class _FakeReq:
    def __init__(self, resource_type: str) -> None:
        self.resource_type = resource_type


class _FakeSubresource:
    """A page subresource response the fake page fires at "response" listeners."""

    def __init__(self, status: int, resource_type: str = "xhr") -> None:
        self.status = status
        self.request = _FakeReq(resource_type)


class _FakePage:
    def __init__(
        self,
        html: str,
        *,
        goto_exc: Exception | None = None,
        goto_sleep: float = 0.0,
        content_sleep: float = 0.0,
        subresources: list[_FakeSubresource] | None = None,
    ) -> None:
        self.closed = False
        self._html = html
        self._goto_exc = goto_exc
        self._goto_sleep = goto_sleep
        self._content_sleep = content_sleep
        self._subresources = subresources or []
        self._listeners: dict[str, list[Any]] = {}
        self.url = "https://example.com/final"
        self.context: Any = None

    def on(self, event: str, cb: Any) -> None:
        self._listeners.setdefault(event, []).append(cb)

    async def goto(self, url: str, **kwargs: Any) -> _Resp:
        if self._goto_sleep:
            await asyncio.sleep(self._goto_sleep)
        if self._goto_exc is not None:
            raise self._goto_exc
        # Fire queued subresource responses at any "response" listener — the seam
        # the backend uses to count challenged XHR/fetch during render.
        for resp in self._subresources:
            for cb in self._listeners.get("response", []):
                cb(resp)
        return _Resp()

    async def content(self) -> str:
        if self._content_sleep:
            await asyncio.sleep(self._content_sleep)
        return self._html

    async def close(self) -> None:
        self.closed = True


class _FakeContext:
    def __init__(self, html: str, **page_kw: Any) -> None:
        self.closed = False
        self.pages: list[_FakePage] = []
        self._html = html
        self._page_kw = page_kw
        self.cookies: list[dict[str, Any]] = []

    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self.cookies.extend(cookies)

    async def new_page(self) -> _FakePage:
        page = _FakePage(self._html, **self._page_kw)
        page.context = self
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self, html: str, **page_kw: Any) -> None:
        self.contexts: list[_FakeContext] = []
        self._html = html
        self._page_kw = page_kw

    async def new_context(self) -> _FakeContext:
        ctx = _FakeContext(self._html, **self._page_kw)
        self.contexts.append(ctx)
        return ctx


class _FakeLaunchCM:
    def __init__(self, browser: _FakeBrowser, *, enter_sleep: float = 0.0) -> None:
        self.browser = browser
        self.exited = False
        self._enter_sleep = enter_sleep

    async def __aenter__(self) -> _FakeBrowser:
        if self._enter_sleep:
            await asyncio.sleep(self._enter_sleep)
        return self.browser

    async def __aexit__(self, *exc: Any) -> None:
        self.exited = True


def _make_backend(
    *,
    html: str = "<html><body>" + ("x" * 5000) + "</body></html>",
    max_pool: int = 4,
    idle_timeout_s: int = 300,
    launch_budget_s: float = 30.0,
    reaper_interval_s: float = 30.0,
    launch_enter_sleep: float = 0.0,
    stderr_sink: Any = None,
    **page_kw: Any,
) -> tuple[PlaywrightBackend, _FakeBrowser, dict[str, _FakeLaunchCM]]:
    browser = _FakeBrowser(html, **page_kw)
    holder: dict[str, _FakeLaunchCM] = {}

    def _launch() -> _FakeLaunchCM:
        cm = _FakeLaunchCM(browser, enter_sleep=launch_enter_sleep)
        holder["cm"] = cm
        return cm

    backend = PlaywrightBackend(
        _launch,
        max_pool=max_pool,
        idle_timeout_s=idle_timeout_s,
        launch_budget_s=launch_budget_s,
        reaper_interval_s=reaper_interval_s,
        stderr_sink=stderr_sink,
    )
    return backend, browser, holder


# --- launch / pool mechanics ------------------------------------------------


@pytest.mark.asyncio
async def test_start_initializes_browser() -> None:
    backend, _browser, holder = _make_backend()
    await backend.start()
    assert "cm" in holder
    await backend.close()
    assert holder["cm"].exited is True


@pytest.mark.asyncio
async def test_same_host_reuses_context() -> None:
    backend, browser, _ = _make_backend()
    await backend.start()
    try:
        async with backend.acquire("https://example.com/a") as page1:
            assert page1 is not None
        async with backend.acquire("https://example.com/b") as page2:
            assert page2 is not None
        assert len(browser.contexts) == 1
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_lru_evicts_oldest_at_cap() -> None:
    backend, browser, _ = _make_backend(max_pool=2)
    await backend.start()
    try:
        async with backend.acquire("https://a.example/"):
            pass
        async with backend.acquire("https://b.example/"):
            pass
        async with backend.acquire("https://c.example/"):
            pass
        assert len(browser.contexts) == 3
        assert browser.contexts[0].closed is True
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_idle_eviction() -> None:
    backend, browser, _ = _make_backend(idle_timeout_s=0)
    await backend.start()
    try:
        async with backend.acquire("https://a.example/"):
            pass
        for ctx in backend._contexts.values():
            ctx.last_used = time.monotonic() - 9999.0
        async with backend.acquire("https://b.example/"):
            pass
        await asyncio.sleep(0)
        assert any(c.closed for c in browser.contexts)
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_close_idempotent() -> None:
    backend, _, _ = _make_backend()
    await backend.start()
    await backend.close()
    await backend.close()  # second close is a no-op


@pytest.mark.asyncio
async def test_acquire_before_start_raises() -> None:
    backend, _, _ = _make_backend()
    with pytest.raises(RuntimeError, match="not started"):
        async with backend.acquire("https://example.com/"):
            pass


# --- render outcomes --------------------------------------------------------


@pytest.mark.asyncio
async def test_render_ok_returns_html() -> None:
    backend, _, _ = _make_backend(html="<html><body>" + ("ok " * 100) + "</body></html>")
    try:
        page = await backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
        assert page.outcome is RenderOutcome.ok
        assert page.js_executed is True
        assert page.status_code == 200
        assert "ok ok" in page.html
        assert page.bytes_transferred == len(page.html)
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_render_error_detail_is_single_line() -> None:
    """A multi-line driver exception collapses to a one-line `detail`."""
    exc = RuntimeError("TypeError: cannot read properties of undefined\n  at FFPage._onUncaughtError\n  at coreBundle.js:49624")
    backend, _, _ = _make_backend(goto_exc=exc)
    try:
        page = await backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
        assert page.outcome is RenderOutcome.error
        assert "\n" not in page.detail
        assert page.detail.startswith("RuntimeError")
        assert "FFPage._onUncaughtError" not in page.detail
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_render_timeout() -> None:
    backend, _, _ = _make_backend(goto_sleep=10.0)
    try:
        page = await backend.render("https://slow.example/", cookies=[], budget_s=0.2, js_heavy=False)
        assert page.outcome is RenderOutcome.timeout
        assert page.js_executed is True
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_render_unavailable_on_launch_timeout() -> None:
    """A launch that hangs past the launch budget must NOT hang the caller — it
    returns `unavailable` within the budget, and the partial launch is cleaned
    up so a later render can retry (never leak a half-open launch CM)."""
    backend, _browser, _holder = _make_backend(launch_enter_sleep=10.0, launch_budget_s=0.2)
    try:
        page = await asyncio.wait_for(
            backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False),
            timeout=3.0,  # test-level guard: if render hangs, fail loudly instead of blocking
        )
        assert page.outcome is RenderOutcome.unavailable
        assert "timed out" in page.detail.lower() or "timeout" in page.detail.lower()
        # The half-open launch CM was torn down (not left dangling to leak).
        assert backend._launch_cm is None
        assert backend._browser is None
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_idle_reaper_closes_browser_when_idle() -> None:
    """A launched-but-idle browser is closed by the background reaper WITHOUT a
    subsequent acquire — bounding resident browser processes so a long-lived
    server can't accumulate 8-hour-old chromium (the leak this fixes)."""
    backend, _browser, holder = _make_backend(idle_timeout_s=0, reaper_interval_s=0.02)
    await backend.start()
    assert backend._browser is not None
    # Wait for the reaper to notice the idle engine and shut it down.
    for _ in range(200):
        if holder["cm"].exited:
            break
        await asyncio.sleep(0.01)
    assert holder["cm"].exited is True  # browser process closed by the reaper
    assert backend._browser is None  # engine put to sleep, re-openable on next use
    assert backend._closed is False  # NOT terminally closed — a later render re-launches
    await backend.close()


@pytest.mark.asyncio
async def test_idle_reaper_relaunches_on_next_render() -> None:
    """After the reaper sleeps the engine, the next render transparently re-launches."""
    backend, _browser, _ = _make_backend(idle_timeout_s=0, reaper_interval_s=0.02, html="<html><body>" + ("ok " * 100) + "</body></html>")
    await backend.start()
    for _ in range(200):
        if backend._browser is None:
            break
        await asyncio.sleep(0.01)
    assert backend._browser is None  # reaped
    try:
        page = await backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
        assert page.outcome is RenderOutcome.ok  # re-launched and served
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_render_timeout_on_hung_content() -> None:
    """`page.content()` hanging past the budget must not hang the caller — it
    resolves to a bounded timeout, not an indefinite block."""
    backend, _, _ = _make_backend(content_sleep=10.0)
    try:
        page = await asyncio.wait_for(
            backend.render("https://slow.example/", cookies=[], budget_s=0.2, js_heavy=False),
            timeout=3.0,
        )
        assert page.outcome is RenderOutcome.timeout
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_render_unavailable_on_launch_import_error() -> None:
    def _boom_launch() -> Any:
        raise ImportError("No module named 'camoufox'")

    backend = PlaywrightBackend(_boom_launch, name="camoufox")
    page = await backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
    assert page.outcome is RenderOutcome.unavailable
    assert "camoufox" in page.detail


# --- driver-stderr capture (drive the pipe directly) ------------------------


async def _drain_until(captured: list[str], n: int) -> None:
    for _ in range(50):
        if len(captured) >= n:
            return
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_stderr_capture_forwards_lines_to_sink() -> None:
    import os

    captured: list[str] = []

    async def sink(line: str) -> None:
        captured.append(line)

    backend, _, _ = _make_backend(stderr_sink=sink)
    saved = backend._install_stderr_capture()
    child_fd = os.dup(backend._stderr_write_fd)
    backend._restore_stderr(saved)
    backend._begin_stderr_drain()
    try:
        os.write(child_fd, b"TypeError: undefined location\nsecond line\n")
        await _drain_until(captured, 2)
    finally:
        os.close(child_fd)
        await backend.close()

    assert captured == ["TypeError: undefined location", "second line"]


@pytest.mark.asyncio
async def test_stderr_capture_silent_when_driver_writes_nothing() -> None:
    import os

    captured: list[str] = []

    async def sink(line: str) -> None:
        captured.append(line)

    backend, _, _ = _make_backend(stderr_sink=sink)
    saved = backend._install_stderr_capture()
    child_fd = os.dup(backend._stderr_write_fd)
    backend._restore_stderr(saved)
    backend._begin_stderr_drain()
    try:
        await asyncio.sleep(0.03)
    finally:
        os.close(child_fd)
        await backend.close()

    assert captured == []


@pytest.mark.asyncio
async def test_no_sink_disables_capture() -> None:
    backend, _, _ = _make_backend()
    saved = backend._install_stderr_capture()
    assert saved is None
    assert backend._stderr_read_fd is None
    backend._restore_stderr(saved)
    backend._begin_stderr_drain()
    await backend.close()


# --- subresource-block evidence (walled-API fake-empty) ----------------------


def test_is_challenged_subresource_predicate() -> None:
    """The counting predicate: XHR/fetch with a challenge status is blocked; a
    document/image or a 200 XHR is not; a malformed response is False, not a raise."""
    from a2web.packages.browser_backends.playwright import _is_challenged_subresource

    assert _is_challenged_subresource(_FakeSubresource(403, "xhr")) is True
    assert _is_challenged_subresource(_FakeSubresource(429, "fetch")) is True
    assert _is_challenged_subresource(_FakeSubresource(401, "xhr")) is True
    assert _is_challenged_subresource(_FakeSubresource(200, "xhr")) is False
    assert _is_challenged_subresource(_FakeSubresource(403, "document")) is False
    assert _is_challenged_subresource(_FakeSubresource(403, "image")) is False
    assert _is_challenged_subresource(object()) is False  # no .request → False, never raises


@pytest.mark.asyncio
async def test_render_counts_blocked_subresources() -> None:
    """A render whose page fires a 403 XHR reports subresource_blocks — the
    walled-API fake-empty signal — while a benign 200 XHR does not count."""
    backend, _, _ = _make_backend(
        html="<html><body>0 results</body></html>",
        subresources=[_FakeSubresource(403, "xhr"), _FakeSubresource(200, "xhr"), _FakeSubresource(429, "fetch")],
    )
    try:
        page = await backend.render("https://shop.example/search?q=x", cookies=[], budget_s=5.0, js_heavy=False)
        assert page.outcome is RenderOutcome.ok
        assert page.subresource_blocks == 2  # the 403 + 429; the 200 does not count
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_render_clean_page_counts_zero_subresources() -> None:
    backend, _, _ = _make_backend(html="<html><body>" + ("ok " * 100) + "</body></html>")
    try:
        page = await backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
        assert page.subresource_blocks == 0
    finally:
        await backend.close()
