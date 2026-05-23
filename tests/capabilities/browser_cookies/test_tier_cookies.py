"""Tier-level tests for cookie pass-through.

Raw tier: cookies dict reaches `curl_cffi.requests.AsyncSession.get(cookies=...)`.
Browser tier: cookies_full list converts to Playwright shape and seeds the
BrowserContext via `add_cookies` BEFORE `page.goto`.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from a2web.cookie_jar import Cookie
from a2web.tiers.browser import BrowserTier, _cookie_to_playwright
from a2web.tiers.raw import RawTier
from tests.conftest import make_default_state

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

    monkeypatch.setattr("a2web.packages.http_fetch.fetch.cr.AsyncSession", _FakeSession)
    state = make_default_state()
    tier = RawTier()
    await tier.fetch("https://example.com/", state=state, cookies=None)
    assert "cookies" not in _FakeSession.last_kwargs


async def test_raw_tier_no_cookies_kwarg_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:

    monkeypatch.setattr("a2web.packages.http_fetch.fetch.cr.AsyncSession", _FakeSession)
    state = make_default_state()
    tier = RawTier()
    await tier.fetch("https://example.com/", state=state, cookies={})
    assert "cookies" not in _FakeSession.last_kwargs


async def test_raw_tier_forwards_cookies(monkeypatch: pytest.MonkeyPatch) -> None:

    monkeypatch.setattr("a2web.packages.http_fetch.fetch.cr.AsyncSession", _FakeSession)
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
    pw = _cookie_to_playwright(c)
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
    pw = _cookie_to_playwright(c)
    assert pw["expires"] == -1
    assert "sameSite" not in pw


def test_playwright_shape_samesite_strict() -> None:
    c = Cookie(name="s", value="v", host_key="x.com", path="/", expires_utc=1, is_secure=0, is_httponly=0, samesite="strict")
    assert _cookie_to_playwright(c)["sameSite"] == "Strict"


def test_playwright_shape_samesite_none() -> None:
    c = Cookie(name="s", value="v", host_key="x.com", path="/", expires_utc=1, is_secure=0, is_httponly=0, samesite="none")
    assert _cookie_to_playwright(c)["sameSite"] == "None"


# --------------------------------------------------------------------- #
# Browser tier — add_cookies ordering vs goto
# --------------------------------------------------------------------- #


class _FakeContext:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self._calls = calls

    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self._calls.append(("add_cookies", cookies))


class _FakeResponseBrowser:
    status = 200


class _FakePage:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self._calls = calls
        self.context = _FakeContext(calls)
        self.url = "https://example.com/"

    async def goto(self, url: str, **kwargs: Any) -> _FakeResponseBrowser:
        self._calls.append(("goto", url))
        return _FakeResponseBrowser()

    async def content(self) -> str:
        return "<html><body><p>" + ("a " * 600) + "</p></body></html>"

    async def close(self) -> None:
        return None


class _FakePool:
    """Drop-in replacement for BrowserPool implementing only the surface BrowserTier uses."""

    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self._calls = calls

    async def _ensure(self) -> None:
        return None

    def acquire(self, url: str):
        calls = self._calls

        class _Ctx:
            async def __aenter__(self_inner) -> _FakePage:
                return _FakePage(calls)

            async def __aexit__(self_inner, *args: Any) -> None:
                return None

        return _Ctx()


async def test_browser_tier_add_cookies_before_goto() -> None:
    state = make_default_state()
    tier = BrowserTier()
    calls: list[tuple[str, Any]] = []
    pool = _FakePool(calls)
    cookies_full = [
        Cookie(name="sid", value="x", host_key=".example.com", path="/", expires_utc=None, is_secure=1, is_httponly=1, samesite="lax"),
    ]
    result = await tier.fetch("https://example.com/", state=state, pool=pool, cookies_full=cookies_full)
    assert result.from_browser
    step_names = [c[0] for c in calls]
    assert step_names == ["add_cookies", "goto"]
    cookies_arg = calls[0][1]
    assert cookies_arg[0]["name"] == "sid"
    assert cookies_arg[0]["domain"] == ".example.com"


async def test_browser_tier_no_add_cookies_when_empty() -> None:
    state = make_default_state()
    tier = BrowserTier()
    calls: list[tuple[str, Any]] = []
    pool = _FakePool(calls)
    await tier.fetch("https://example.com/", state=state, pool=pool, cookies_full=None)
    step_names = [c[0] for c in calls]
    assert step_names == ["goto"]
