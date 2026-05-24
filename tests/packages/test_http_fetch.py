"""http_fetch primitive tests — curl_cffi via monkeypatched AsyncSession.

Covers pure helpers, then `fetch_bytes` across each verdict branch via a
fake `AsyncSession` injected at the package's curl_cffi import path.
"""

from __future__ import annotations

from typing import Any

import pytest
from curl_cffi.requests import exceptions as ce

from a2web.packages.http_fetch import FetchOutcome, FetchVerdict, fetch_bytes
from a2web.packages.http_fetch.fetch import (
    _conditional_headers,
    _is_proxy_error,
    _status_to_verdict,
)

# --------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------- #


class TestConditionalHeaders:
    def test_empty_extras(self) -> None:
        assert _conditional_headers(None) == {}
        assert _conditional_headers({}) == {}

    def test_etag_only(self) -> None:
        assert _conditional_headers({"etag": '"abc"'}) == {"If-None-Match": '"abc"'}

    def test_last_modified_only(self) -> None:
        assert _conditional_headers({"last_modified": "Wed, 21 Oct"}) == {"If-Modified-Since": "Wed, 21 Oct"}

    def test_both(self) -> None:
        out = _conditional_headers({"etag": '"x"', "last_modified": "now"})
        assert out == {"If-None-Match": '"x"', "If-Modified-Since": "now"}

    def test_empty_string_etag_skipped(self) -> None:
        assert _conditional_headers({"etag": ""}) == {}

    def test_non_string_value_skipped(self) -> None:
        assert _conditional_headers({"etag": 12345}) == {}


class TestIsProxyError:
    def test_proxy_keyword(self) -> None:
        assert _is_proxy_error(RuntimeError("proxy refused"))

    def test_socks_keyword(self) -> None:
        assert _is_proxy_error(RuntimeError("SOCKS5 handshake"))

    def test_tunnel_keyword(self) -> None:
        assert _is_proxy_error(RuntimeError("tunnel failed"))

    def test_non_proxy_error(self) -> None:
        assert not _is_proxy_error(RuntimeError("connection reset"))


class TestStatusToVerdict:
    def test_200_ok(self) -> None:
        assert _status_to_verdict(200) is FetchVerdict.ok

    def test_404_not_found(self) -> None:
        assert _status_to_verdict(404) is FetchVerdict.not_found

    def test_429_rate_limited(self) -> None:
        assert _status_to_verdict(429) is FetchVerdict.rate_limited

    def test_other_4xx_connection_error(self) -> None:
        assert _status_to_verdict(403) is FetchVerdict.connection_error

    def test_5xx_connection_error(self) -> None:
        assert _status_to_verdict(503) is FetchVerdict.connection_error


# --------------------------------------------------------------------- #
# fetch_bytes — mocked curl_cffi AsyncSession
# --------------------------------------------------------------------- #


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"<html>ok</html>",
        content_type: str = "text/html",
        url: str = "https://example.com/",
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.url = url
        self.headers = {"content-type": content_type}


class _FakeSession:
    def __init__(self, payload: _FakeResponse | BaseException) -> None:
        self._payload = payload
        self.last_request: dict[str, Any] = {}
        self.session_kwargs: dict[str, Any] = {}

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.last_request = {"url": url, **kwargs}
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


def _patch_session(monkeypatch: pytest.MonkeyPatch, payload: _FakeResponse | BaseException) -> _FakeSession:
    fake = _FakeSession(payload)

    def _factory(**kw: Any) -> _FakeSession:
        fake.session_kwargs = kw
        return fake

    monkeypatch.setattr("a2web.packages.http_fetch.fetch.cr.AsyncSession", _factory)
    return fake


@pytest.mark.asyncio
async def test_chrome_impersonation_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await fetch_bytes("https://example.com/")
    assert fake.session_kwargs.get("impersonate", "").startswith("chrome")


@pytest.mark.asyncio
async def test_200_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse(content=b"<html>hi</html>"))
    result = await fetch_bytes("https://example.com/")
    assert isinstance(result, FetchOutcome)
    assert result.verdict is FetchVerdict.ok
    assert result.status_code == 200
    assert result.body == b"<html>hi</html>"
    assert result.content_type == "text/html"
    assert result.conditional_hit is False


@pytest.mark.asyncio
async def test_404_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse(status_code=404))
    result = await fetch_bytes("https://example.com/missing")
    assert result.verdict is FetchVerdict.not_found


@pytest.mark.asyncio
async def test_429_returns_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse(status_code=429))
    assert (await fetch_bytes("https://example.com/")).verdict is FetchVerdict.rate_limited


@pytest.mark.asyncio
async def test_5xx_returns_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse(status_code=503))
    assert (await fetch_bytes("https://example.com/")).verdict is FetchVerdict.connection_error


@pytest.mark.asyncio
async def test_timeout_returns_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, ce.Timeout("connect timeout"))
    result = await fetch_bytes("https://example.com/")
    assert result.verdict is FetchVerdict.timeout
    assert result.status_code == 0


@pytest.mark.asyncio
async def test_generic_request_exception_returns_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, ce.RequestException("DNS failure"))
    assert (await fetch_bytes("https://example.com/")).verdict is FetchVerdict.connection_error


@pytest.mark.asyncio
async def test_proxy_error_with_proxy_url_returns_proxy_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, ce.RequestException("SOCKS5 proxy refused"))
    result = await fetch_bytes("https://example.com/", proxy_url="socks5://localhost:1080")
    assert result.verdict is FetchVerdict.proxy_unavailable


@pytest.mark.asyncio
async def test_proxy_shaped_error_without_proxy_is_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, ce.RequestException("SOCKS5 refused"))
    assert (await fetch_bytes("https://example.com/")).verdict is FetchVerdict.connection_error


@pytest.mark.asyncio
async def test_proxy_url_is_plumbed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await fetch_bytes("https://example.com/", proxy_url="http://proxy:8080")
    assert fake.last_request["proxies"] == {"http": "http://proxy:8080", "https": "http://proxy:8080"}


@pytest.mark.asyncio
async def test_no_proxy_url_omits_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await fetch_bytes("https://example.com/")
    assert "proxies" not in fake.last_request


@pytest.mark.asyncio
async def test_cookies_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await fetch_bytes("https://example.com/", cookies={"sid": "x"})
    assert fake.last_request["cookies"] == {"sid": "x"}


@pytest.mark.asyncio
async def test_empty_cookies_dict_not_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await fetch_bytes("https://example.com/", cookies={})
    assert "cookies" not in fake.last_request


@pytest.mark.asyncio
async def test_304_returns_conditional_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse(status_code=304, content=b""))
    result = await fetch_bytes(
        "https://example.com/",
        conditional_extras={"etag": '"abc"'},
    )
    assert result.verdict is FetchVerdict.ok
    assert result.status_code == 304
    assert result.conditional_hit is True
    assert result.body == b""


@pytest.mark.asyncio
async def test_conditional_extras_become_request_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await fetch_bytes(
        "https://example.com/",
        headers={"User-Agent": "UA"},
        conditional_extras={"etag": '"abc"', "last_modified": "Wed, 21 Oct"},
    )
    sent = fake.last_request["headers"]
    assert sent["User-Agent"] == "UA"
    assert sent["If-None-Match"] == '"abc"'
    assert sent["If-Modified-Since"] == "Wed, 21 Oct"


@pytest.mark.asyncio
async def test_custom_headers_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await fetch_bytes("https://example.com/", headers={"User-Agent": "MyAgent/1.0", "X-Custom": "v"})
    assert fake.last_request["headers"]["User-Agent"] == "MyAgent/1.0"
    assert fake.last_request["headers"]["X-Custom"] == "v"


# --- breaker integration ---


class _FakeBreaker:
    def __init__(self, *, raise_on_enter: bool = False) -> None:
        self.entered = False
        self.raise_on_enter = raise_on_enter

    async def __aenter__(self) -> _FakeBreaker:
        if self.raise_on_enter:
            msg = "breaker open"
            raise RuntimeError(msg)
        self.entered = True
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_breaker_wraps_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse())
    breaker = _FakeBreaker()
    result = await fetch_bytes("https://example.com/", breaker=breaker)
    assert breaker.entered is True
    assert result.verdict is FetchVerdict.ok


@pytest.mark.asyncio
async def test_breaker_open_returns_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse())
    breaker = _FakeBreaker(raise_on_enter=True)
    result = await fetch_bytes("https://example.com/", breaker=breaker)
    assert result.verdict is FetchVerdict.connection_error


# --- no secret leakage ---


@pytest.mark.asyncio
async def test_cookies_not_in_outcome_diagnostic_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """A FetchOutcome's repr / fields must not surface cookie values."""
    _patch_session(monkeypatch, _FakeResponse())
    result = await fetch_bytes("https://example.com/", cookies={"sid": "supersecret"})
    rendered = repr(result)
    assert "supersecret" not in rendered
