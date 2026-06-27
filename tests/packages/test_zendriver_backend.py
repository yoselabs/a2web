"""ZendriverBackend — CDP adapter outcome mapping.

Tests inject a fake `zendriver` module (no real Chromium/CDP). Real-binary
coverage rides the bake-off + the `browser`-marked smoke. Mirrors
`test_playwright_backend.py`'s render-outcome section.
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from a2web.packages.browser_backends import BackendCookie, RenderOutcome
from a2web.packages.browser_backends.zendriver import ZendriverBackend


class _FakeTab:
    def __init__(self, html: str, *, content_exc: Exception | None = None, content_sleep: float = 0.0) -> None:
        self.url = "https://example.com/final"
        self._html = html
        self._content_exc = content_exc
        self._content_sleep = content_sleep

    async def wait_for_ready_state(self, until: str = "complete", timeout: int = 10) -> bool:  # noqa: ASYNC109 - mirrors zendriver's real Tab signature
        return True

    async def get_content(self) -> str:
        if self._content_sleep:
            await asyncio.sleep(self._content_sleep)
        if self._content_exc is not None:
            raise self._content_exc
        return self._html

    async def scroll_down(self, amount: int = 25, speed: int = 800) -> None:
        return None


class _FakeCookieJar:
    def __init__(self) -> None:
        self.set_calls: list[list[Any]] = []

    async def set_all(self, cookies: list[Any]) -> None:
        self.set_calls.append(cookies)


class _FakeBrowser:
    def __init__(self, tab: _FakeTab) -> None:
        self._tab = tab
        self.cookies = _FakeCookieJar()
        self.stopped = False

    async def get(self, url: str = "about:blank", new_tab: bool = False, new_window: bool = False) -> _FakeTab:
        return self._tab

    async def stop(self) -> None:
        self.stopped = True


class _CookieSameSite:
    STRICT = "Strict"
    LAX = "Lax"
    NONE = "None"


class _CookieParam:
    def __init__(self, **kw: Any) -> None:
        self.kw = kw


def _install_fake_zendriver(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tab: _FakeTab | None = None,
    start_exc: Exception | None = None,
    import_error: bool = False,
) -> dict[str, Any]:
    """Inject a fake `zendriver` module; return a holder exposing the browser."""
    holder: dict[str, Any] = {}
    if import_error:
        monkeypatch.setitem(sys.modules, "zendriver", None)  # `import zendriver` → ImportError
        return holder

    mod = types.ModuleType("zendriver")

    class _Config:
        def __init__(self, headless: bool = False) -> None:
            self.headless = headless
            self.browser_connection_timeout = 0.25
            self.browser_connection_max_tries = 10

    async def _start(*, config: Any) -> _FakeBrowser:
        if start_exc is not None:
            raise start_exc
        browser = _FakeBrowser(tab or _FakeTab("<html></html>"))
        holder["browser"] = browser
        return browser

    cdp = types.SimpleNamespace(network=types.SimpleNamespace(CookieParam=_CookieParam, CookieSameSite=_CookieSameSite))
    mod.Config = _Config  # type: ignore[attr-defined]
    mod.start = _start  # type: ignore[attr-defined]
    mod.cdp = cdp  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "zendriver", mod)
    return holder


@pytest.mark.asyncio
async def test_render_ok_returns_html(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_zendriver(monkeypatch, tab=_FakeTab("<html><body>" + ("ok " * 100) + "</body></html>"))
    backend = ZendriverBackend()
    page = await backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
    assert page.outcome is RenderOutcome.ok
    assert page.js_executed is True
    assert page.status_code == 200
    assert "ok ok" in page.html
    assert page.final_url == "https://example.com/final"
    assert page.bytes_transferred == len(page.html)


@pytest.mark.asyncio
async def test_render_seeds_cookies_before_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _install_fake_zendriver(monkeypatch, tab=_FakeTab("<html>x</html>"))
    backend = ZendriverBackend()
    cookies = [
        BackendCookie(name="t", value="1", domain="example.com", path="/", expires=None, secure=True, http_only=False, samesite="lax"),
    ]
    await backend.render("https://example.com/", cookies=cookies, budget_s=5.0, js_heavy=False)
    browser = holder["browser"]
    assert len(browser.cookies.set_calls) == 1
    assert len(browser.cookies.set_calls[0]) == 1  # one CookieParam built


@pytest.mark.asyncio
async def test_render_error_detail_is_single_line(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = RuntimeError("CDP error: target crashed\n  at Connection.send\n  at Tab.get_content")
    _install_fake_zendriver(monkeypatch, tab=_FakeTab("", content_exc=exc))
    backend = ZendriverBackend()
    page = await backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
    assert page.outcome is RenderOutcome.error
    assert "\n" not in page.detail
    assert page.detail.startswith("RuntimeError")
    assert "Connection.send" not in page.detail


@pytest.mark.asyncio
async def test_render_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_zendriver(monkeypatch, tab=_FakeTab("<html>x</html>", content_sleep=10.0))
    backend = ZendriverBackend()
    page = await backend.render("https://slow.example/", cookies=[], budget_s=0.2, js_heavy=False)
    assert page.outcome is RenderOutcome.timeout
    assert page.js_executed is True


@pytest.mark.asyncio
async def test_render_unavailable_on_launch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_zendriver(monkeypatch, start_exc=Exception("Failed to connect to browser"))
    backend = ZendriverBackend()
    page = await backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
    assert page.outcome is RenderOutcome.unavailable
    assert "launch failed" in page.detail


@pytest.mark.asyncio
async def test_render_unavailable_when_zendriver_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_zendriver(monkeypatch, import_error=True)
    backend = ZendriverBackend()
    page = await backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
    assert page.outcome is RenderOutcome.unavailable
    assert "not installed" in page.detail


@pytest.mark.asyncio
async def test_browser_stopped_after_render(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _install_fake_zendriver(monkeypatch, tab=_FakeTab("<html>x</html>"))
    backend = ZendriverBackend()
    await backend.render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
    assert holder["browser"].stopped is True
