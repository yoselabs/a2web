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
from a2web.packages.browser_backends.zendriver import ZendriverBackend, _resolve_executable


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
        """Mirrors the real `zd.Config` surface the backend touches.

        `browser_executable_path` + `add_argument` are part of the genuine API
        (verified against the installed zendriver); the real default is an
        auto-discovered SYSTEM Chrome path, which is precisely why a container
        with only a Playwright-managed Chromium finds nothing.
        """

        def __init__(self, headless: bool = False) -> None:
            self.headless = headless
            self.browser_connection_timeout = 0.25
            self.browser_connection_max_tries = 10
            self.browser_executable_path = "/system/chrome"
            self.arguments: list[str] = []

        def add_argument(self, arg: str) -> None:
            self.arguments.append(arg)

    async def _start(*, config: Any) -> _FakeBrowser:
        holder["config"] = config  # captured even on failure, for launch assertions
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


# --------------------------------------------------------------------- #
# Container launch: binary resolution + startup flags + failure diagnosis
#
# The published image bakes Chromium in under PLAYWRIGHT_BROWSERS_PATH for
# patchright, but zendriver defaults to auto-discovering a SYSTEM Chrome that no
# container has — so the robust rung was dead in every deployed image while
# reporting only zendriver's opaque "Failed to connect to browser".
# --------------------------------------------------------------------- #


def _clear_browser_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("A2WEB_BROWSER_EXECUTABLE_PATH", "PLAYWRIGHT_BROWSERS_PATH"):
        monkeypatch.delenv(var, raising=False)


def test_resolve_executable_none_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No hints → None, i.e. defer to zendriver's own discovery (dev machines)."""
    _clear_browser_env(monkeypatch)
    assert _resolve_executable() is None


def test_resolve_executable_prefers_explicit_override(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _clear_browser_env(monkeypatch)
    monkeypatch.setenv("A2WEB_BROWSER_EXECUTABLE_PATH", "/custom/chrome")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert _resolve_executable() == "/custom/chrome"


def test_resolve_executable_finds_playwright_chromium(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """The published-image layout: <root>/chromium-<build>/chrome-linux64/chrome."""
    _clear_browser_env(monkeypatch)
    binary = tmp_path / "chromium-1223" / "chrome-linux64" / "chrome"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert _resolve_executable() == str(binary)


def test_resolve_executable_picks_highest_build(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Two installs in one image → the newer build wins."""
    _clear_browser_env(monkeypatch)
    for build in ("chromium-1100", "chromium-1223"):
        binary = tmp_path / build / "chrome-linux64" / "chrome"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert _resolve_executable() == str(tmp_path / "chromium-1223" / "chrome-linux64" / "chrome")


@pytest.mark.asyncio
async def test_render_passes_resolved_binary_and_container_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """The resolved path and the container startup flags reach zd.Config."""
    _clear_browser_env(monkeypatch)
    monkeypatch.setenv("A2WEB_BROWSER_EXECUTABLE_PATH", "/opt/browsers/chrome")
    holder = _install_fake_zendriver(monkeypatch, tab=_FakeTab("<html>" + ("x " * 200) + "</html>"))
    await ZendriverBackend().render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
    config = holder["config"]
    assert config.browser_executable_path == "/opt/browsers/chrome"
    assert "--no-sandbox" in config.arguments
    assert "--disable-dev-shm-usage" in config.arguments


@pytest.mark.asyncio
async def test_launch_failure_reports_no_binary_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing resolvable, the detail names the fix — not a connect timeout."""
    _clear_browser_env(monkeypatch)
    _install_fake_zendriver(monkeypatch, start_exc=RuntimeError("Failed to connect to browser"))
    page = await ZendriverBackend().render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
    assert page.outcome is RenderOutcome.unavailable
    assert "no Chromium resolved" in page.detail
    assert "A2WEB_BROWSER_EXECUTABLE_PATH" in page.detail


@pytest.mark.asyncio
async def test_launch_failure_reports_missing_resolved_binary(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """A resolved-but-absent binary is named explicitly."""
    _clear_browser_env(monkeypatch)
    missing = tmp_path / "ghost-chrome"
    monkeypatch.setenv("A2WEB_BROWSER_EXECUTABLE_PATH", str(missing))
    _install_fake_zendriver(monkeypatch, start_exc=RuntimeError("Failed to connect to browser"))
    page = await ZendriverBackend().render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
    assert page.outcome is RenderOutcome.unavailable
    assert "does not exist" in page.detail
    assert str(missing) in page.detail


@pytest.mark.asyncio
async def test_launch_failure_distinguishes_healthy_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    """A binary that runs fine → the failure is the CDP handshake, and the
    detail says so. This is the discrimination that was missing: 'no binary' and
    'binary present, handshake failed' need opposite operator actions."""
    _clear_browser_env(monkeypatch)
    monkeypatch.setenv("A2WEB_BROWSER_EXECUTABLE_PATH", "/bin/echo")  # exits 0
    _install_fake_zendriver(monkeypatch, start_exc=RuntimeError("Failed to connect to browser"))
    page = await ZendriverBackend().render("https://example.com/", cookies=[], budget_s=5.0, js_heavy=False)
    assert page.outcome is RenderOutcome.unavailable
    assert "CDP handshake" in page.detail
