"""Tests for the browser-cookie3 adapter (`packages/cookie_store/store.py`).

Replaces the v0.8 `test_cookie_store_chrome_decrypt.py` and
`test_cookie_store_firefox.py` suites. browser-cookie3 owns the decryption
and per-OS file discovery; we only test the dispatch + boundary mapping
and the error wrapping discipline.
"""

from __future__ import annotations

from http.cookiejar import Cookie, CookieJar

import pytest

from a2web.packages.cookie_store import CookieAccessError, read_cookies
from a2web.packages.cookie_store.models import CookieRow

# --------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------- #


def _make_cookie(
    name: str = "sid",
    value: str = "abc",
    domain: str = ".example.com",
    path: str = "/",
    secure: bool = True,
    expires: int | None = 2_000_000_000,
    httponly: bool = False,
    samesite: str | None = "Lax",
) -> Cookie:
    rest: dict[str, str] = {}
    if httponly:
        rest["HttpOnly"] = ""
    if samesite is not None:
        rest["SameSite"] = samesite
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path=path,
        path_specified=True,
        secure=secure,
        expires=expires,
        discard=False,
        comment=None,
        comment_url=None,
        rest=rest,
        rfc2109=False,
    )


def _jar(*cookies: Cookie) -> CookieJar:
    jar = CookieJar()
    for c in cookies:
        jar.set_cookie(c)
    return jar


@pytest.fixture
def patch_bc3(monkeypatch: pytest.MonkeyPatch):
    """Install a per-browser stub on the browser_cookie3 module."""
    import browser_cookie3 as bc3

    captured: dict[str, list[tuple[str, str | None]]] = {}

    def factory(name: str):
        def fn(domain_name: str = "", **_kw: object) -> CookieJar:
            captured.setdefault(name, []).append((name, domain_name or None))
            return _jar(_make_cookie())

        return fn

    for browser in (
        "chrome",
        "chromium",
        "brave",
        "edge",
        "firefox",
        "safari",
        "vivaldi",
        "opera",
        "opera_gx",
    ):
        monkeypatch.setattr(bc3, browser, factory(browser))

    return captured


# --------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "source",
    [
        "chrome",
        "chromium",
        "brave",
        "edge",
        "firefox",
        "safari",
        "vivaldi",
        "opera",
        "opera_gx",
    ],
)
def test_read_cookies_dispatches_to_correct_browser(
    source: str,
    patch_bc3: dict[str, list[tuple[str, str | None]]],
) -> None:
    rows = read_cookies(source)  # type: ignore[arg-type]
    assert len(rows) == 1
    assert source in patch_bc3
    assert patch_bc3[source] == [(source, None)]


def test_read_cookies_maps_cookie_fields_to_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import browser_cookie3 as bc3

    cookie = _make_cookie(
        name="session",
        value="topsecret",
        domain=".reddit.com",
        path="/api",
        secure=True,
        expires=1_900_000_000,
        httponly=True,
        samesite="Strict",
    )
    monkeypatch.setattr(bc3, "chrome", lambda **_kw: _jar(cookie))

    rows = read_cookies("chrome")
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, CookieRow)
    assert row.name == "session"
    assert row.value == "topsecret"
    assert row.host_key == ".reddit.com"
    assert row.path == "/api"
    assert row.expires_utc == 1_900_000_000
    assert row.is_secure == 1
    assert row.is_httponly == 1
    assert row.samesite == "strict"


def test_session_cookie_expires_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    import browser_cookie3 as bc3

    cookie = _make_cookie(expires=None)
    monkeypatch.setattr(bc3, "chrome", lambda **_kw: _jar(cookie))

    rows = read_cookies("chrome")
    assert rows[0].expires_utc is None


def test_unknown_samesite_normalizes_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    import browser_cookie3 as bc3

    cookie = _make_cookie(samesite="garbage")
    monkeypatch.setattr(bc3, "chrome", lambda **_kw: _jar(cookie))

    rows = read_cookies("chrome")
    assert rows[0].samesite is None


def test_read_cookies_wraps_upstream_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    import browser_cookie3 as bc3

    class _SecretLeakingError(Exception):
        pass

    def _boom(**_kw: object) -> CookieJar:
        raise _SecretLeakingError("AES key: deadbeef ; cookie value: topsecret")

    monkeypatch.setattr(bc3, "chrome", _boom)

    with pytest.raises(CookieAccessError) as exc_info:
        read_cookies("chrome")

    # Message must NOT carry the secret material; only structural context.
    msg = str(exc_info.value)
    assert "deadbeef" not in msg
    assert "topsecret" not in msg
    assert "chrome" in msg
    assert "_SecretLeakingError" in msg
    assert isinstance(exc_info.value.__cause__, _SecretLeakingError)


def test_unsupported_source_raises_cookie_access_error() -> None:
    with pytest.raises(CookieAccessError):
        read_cookies("nope")  # type: ignore[arg-type]


def test_missing_extra_degrades_to_cookie_access_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """`browser-cookie3` is the optional `[cookies]` extra. When absent, the
    deferred import must degrade to `CookieAccessError` with an actionable
    'install a2web[cookies]' message — not a raw ModuleNotFoundError. (Setting
    sys.modules[name]=None makes `import browser_cookie3` raise ModuleNotFoundError,
    simulating the extra being uninstalled.)"""
    import sys

    monkeypatch.setitem(sys.modules, "browser_cookie3", None)
    with pytest.raises(CookieAccessError) as exc_info:
        read_cookies("chrome")
    assert "a2web[cookies]" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ModuleNotFoundError)
