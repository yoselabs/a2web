"""Tier-level tests for cookie pass-through.

Raw tier: cookies dict reaches `curl_cffi.requests.AsyncSession.get(cookies=...)`.
Browser tier: cookies_full list converts to Playwright shape and seeds the
BrowserContext via `add_cookies` BEFORE `page.goto`.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from a2web.cookie_jar import Cookie
from a2web.packages.browser_backends import PlaywrightBackend
from a2web.packages.browser_backends.playwright import _cookie_to_playwright
from a2web.tiers.browser import BrowserTier, _cookie_to_backend
from a2web.tiers.raw import RawTier
from tests.conftest import make_default_state


def _pw(c: Cookie) -> dict[str, Any]:
    """Domain Cookie → BackendCookie (tier) → Playwright shape (backend)."""
    return _cookie_to_playwright(_cookie_to_backend(c))


# --------------------------------------------------------------------- #
# Raw tier
# --------------------------------------------------------------------- #


class _FakeResponse:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {"content-type": "text/html"}
        self.content = b"<html></html>"
        self.status_code = 200
        self.url = "https://example.com/"


class _FakeSession:
    """Captures the get() kwargs for assertion."""

    last_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        type(self).last_kwargs = kwargs
        return _FakeResponse()


async def test_raw_tier_no_cookies_kwarg_when_none(monkeypatch: pytest.MonkeyPatch) -> None:

    monkeypatch.setattr("http_fetch.fetch.cr.AsyncSession", _FakeSession)
    state = make_default_state()
    tier = RawTier()
    await tier.fetch("https://example.com/", state=state, cookies=None)
    assert "cookies" not in _FakeSession.last_kwargs


async def test_raw_tier_no_cookies_kwarg_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:

    monkeypatch.setattr("http_fetch.fetch.cr.AsyncSession", _FakeSession)
    state = make_default_state()
    tier = RawTier()
    await tier.fetch("https://example.com/", state=state, cookies={})
    assert "cookies" not in _FakeSession.last_kwargs


async def test_raw_tier_forwards_cookies(monkeypatch: pytest.MonkeyPatch) -> None:

    monkeypatch.setattr("http_fetch.fetch.cr.AsyncSession", _FakeSession)
    state = make_default_state()
    tier = RawTier()
    await tier.fetch("https://example.com/", state=state, cookies={"sid": "x", "csrf": "y"})
    assert _FakeSession.last_kwargs["cookies"] == {"sid": "x", "csrf": "y"}


# --------------------------------------------------------------------- #
# Browser tier — Playwright shape conversion
# --------------------------------------------------------------------- #


def test_playwright_shape_basic() -> None:
    c = Cookie(
        name="sid",
        value="x",
        host_key=".example.com",
        path="/",
        expires_utc=None,
        is_secure=1,
        is_httponly=1,
        samesite="lax",
    )
    pw = _pw(c)
    assert pw == {
        "name": "sid",
        "value": "x",
        "domain": ".example.com",
        "path": "/",
        "expires": -1,
        "secure": True,
        "httpOnly": True,
        "sameSite": "Lax",
    }


def test_playwright_shape_session_cookie_expires_minus_one() -> None:
    c = Cookie(name="s", value="v", host_key="x.com", path="/", expires_utc=None, is_secure=0, is_httponly=0, samesite=None)
    pw = _pw(c)
    assert pw["expires"] == -1
    assert "sameSite" not in pw


def test_playwright_shape_samesite_strict() -> None:
    c = Cookie(name="s", value="v", host_key="x.com", path="/", expires_utc=1, is_secure=0, is_httponly=0, samesite="strict")
    assert _pw(c)["sameSite"] == "Strict"


def test_playwright_shape_samesite_none() -> None:
    c = Cookie(name="s", value="v", host_key="x.com", path="/", expires_utc=1, is_secure=0, is_httponly=0, samesite="none")
    assert _pw(c)["sameSite"] == "None"


# --------------------------------------------------------------------- #
# Browser tier — add_cookies ordering vs goto
# --------------------------------------------------------------------- #


# Cookie-seeding-before-navigation is now realized inside `PlaywrightBackend`;
# these tests drive a real backend with a fake (no-Camoufox) launcher and
# assert the call order through the tier → backend seam.


class _FakeResponseBrowser:
    status = 200


class _FakeContext:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self._calls = calls

    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self._calls.append(("add_cookies", cookies))

    async def new_page(self) -> _FakePage:
        return _FakePage(self, self._calls)

    async def close(self) -> None:
        return None


class _FakePage:
    def __init__(self, context: _FakeContext, calls: list[tuple[str, Any]]) -> None:
        self.context = context
        self._calls = calls
        self.url = "https://example.com/"

    async def goto(self, url: str, **kwargs: Any) -> _FakeResponseBrowser:
        self._calls.append(("goto", url))
        return _FakeResponseBrowser()

    async def content(self) -> str:
        return "<html><body><p>" + ("a " * 600) + "</p></body></html>"

    async def close(self) -> None:
        return None


class _FakeBrowser:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self._calls = calls

    async def new_context(self) -> _FakeContext:
        return _FakeContext(self._calls)


class _FakeLaunchCM:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self._calls = calls

    async def __aenter__(self) -> _FakeBrowser:
        return _FakeBrowser(self._calls)

    async def __aexit__(self, *_: Any) -> None:
        return None


def _fake_backend(calls: list[tuple[str, Any]]) -> PlaywrightBackend:
    def _launch() -> _FakeLaunchCM:
        return _FakeLaunchCM(calls)

    return PlaywrightBackend(_launch, name="fake")


async def test_browser_tier_add_cookies_before_goto() -> None:
    state = make_default_state()
    calls: list[tuple[str, Any]] = []
    backend = _fake_backend(calls)
    cookies_full = [
        Cookie(name="sid", value="x", host_key=".example.com", path="/", expires_utc=None, is_secure=1, is_httponly=1, samesite="lax"),
    ]
    result = await BrowserTier().fetch("https://example.com/", state=state, backend=backend, cookies_full=cookies_full)
    assert result.from_browser
    step_names = [c[0] for c in calls]
    assert step_names == ["add_cookies", "goto"]
    cookies_arg = calls[0][1]
    assert cookies_arg[0]["name"] == "sid"
    assert cookies_arg[0]["domain"] == ".example.com"
    await backend.close()


async def test_browser_tier_no_add_cookies_when_empty() -> None:
    state = make_default_state()
    calls: list[tuple[str, Any]] = []
    backend = _fake_backend(calls)
    await BrowserTier().fetch("https://example.com/", state=state, backend=backend, cookies_full=None)
    step_names = [c[0] for c in calls]
    assert step_names == ["goto"]
    await backend.close()
