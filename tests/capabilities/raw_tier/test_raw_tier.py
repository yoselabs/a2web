"""RawTier tests — curl_cffi via monkeypatched AsyncSession.

Covers the pure helpers (`_verdict_for_status`, `_is_proxy_error`,
`_conditional_headers`) directly, then `RawTier.fetch` over each
verdict branch via a fake `AsyncSession` injected at `curl_cffi`'s
import path.
"""

from __future__ import annotations

from typing import Any

import pytest
from curl_cffi.requests import exceptions as curl_exceptions

from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers.raw import RawTier, _verdict_for_status
from tests.conftest import make_default_state


def _state(**kwargs: object) -> AppState:
    return make_default_state(settings=AppSettings(**kwargs))


# --------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------- #


class TestVerdictForStatus:
    def test_404_maps_to_not_found(self) -> None:
        assert _verdict_for_status(404, "text/html") == Verdict.not_found

    def test_429_maps_to_rate_limited(self) -> None:
        assert _verdict_for_status(429, "text/html") == Verdict.rate_limited

    def test_5xx_maps_to_connection_error(self) -> None:
        assert _verdict_for_status(500, "text/html") == Verdict.connection_error
        assert _verdict_for_status(503, "text/html") == Verdict.connection_error

    def test_other_4xx_maps_to_connection_error(self) -> None:
        # 403 / 401 / 410 all map to connection_error; only 404/429 are special-cased.
        assert _verdict_for_status(403, "text/html") == Verdict.connection_error
        assert _verdict_for_status(401, "text/html") == Verdict.connection_error

    def test_json_content_type_is_ok(self) -> None:
        # json-endpoint-direct-routing: a JSON response is first-class content,
        # not a mismatch — it is synthesized downstream, never sent to jina.
        assert _verdict_for_status(200, "application/json") == Verdict.ok
        assert _verdict_for_status(200, "application/json; charset=utf-8") == Verdict.ok
        assert _verdict_for_status(200, "application/vnd.api+json") == Verdict.ok
        assert _verdict_for_status(200, "text/json") == Verdict.ok

    def test_non_html_non_json_content_type_mismatches(self) -> None:
        # Only JSON is carved out; other non-HTML bodies still mismatch/escalate.
        assert _verdict_for_status(200, "application/pdf") == Verdict.content_type_mismatch
        assert _verdict_for_status(200, "application/octet-stream") == Verdict.content_type_mismatch

    def test_html_content_type_ok(self) -> None:
        assert _verdict_for_status(200, "text/html") == Verdict.ok
        assert _verdict_for_status(200, "text/html; charset=utf-8") == Verdict.ok

    def test_content_type_match_is_case_insensitive(self) -> None:
        assert _verdict_for_status(200, "TEXT/HTML") == Verdict.ok


# Helper unit tests for `_is_proxy_error` / `_conditional_headers` moved to
# `tests/packages/test_http_fetch.py` — those helpers live in the shared
# `http_fetch` primitive now.


# --------------------------------------------------------------------- #
# RawTier.fetch — mocked curl_cffi AsyncSession
# --------------------------------------------------------------------- #


class _FakeResponse:
    """Stand-in for curl_cffi's Response."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"<html>ok</html>",
        content_type: str = "text/html",
        url: str = "https://example.com/",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.url = url
        self.headers = {"content-type": content_type}
        if extra_headers:
            self.headers.update(extra_headers)


class _FakeSession:
    """Async-context-manager fake for `curl_requests.AsyncSession`."""

    def __init__(self, response_or_exc: _FakeResponse | BaseException) -> None:
        self._payload = response_or_exc
        self.last_request: dict[str, Any] = {}

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
    """Replace `curl_requests.AsyncSession` with one that yields `payload`."""
    fake = _FakeSession(payload)
    monkeypatch.setattr(
        "a2web.packages.http_fetch.fetch.cr.AsyncSession",
        lambda **kw: fake,
    )
    return fake


@pytest.mark.asyncio
async def test_fetch_200_html_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse(content=b"<html>hello</html>"))
    result = await RawTier().fetch("https://example.com/x", state=_state())
    assert result.verdict == Verdict.ok
    assert result.status_code == 200
    assert result.body == b"<html>hello</html>"
    assert result.content_type == "text/html"


@pytest.mark.asyncio
async def test_fetch_404_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse(status_code=404))
    result = await RawTier().fetch("https://example.com/missing", state=_state())
    assert result.verdict == Verdict.not_found
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_fetch_429_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse(status_code=429))
    result = await RawTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.rate_limited


@pytest.mark.asyncio
async def test_fetch_304_returns_conditional_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, _FakeResponse(status_code=304, content=b""))
    result = await RawTier().fetch(
        "https://example.com/",
        state=_state(),
        conditional_extras={"etag": '"abc"', "last_modified": "now"},
    )
    assert result.verdict == Verdict.ok
    assert result.status_code == 304
    assert result.conditional_hit is True


@pytest.mark.asyncio
async def test_fetch_timeout_returns_timeout_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, curl_exceptions.Timeout("connect timeout"))
    result = await RawTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.timeout
    assert result.status_code == 0


@pytest.mark.asyncio
async def test_fetch_generic_request_error_is_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, curl_exceptions.RequestException("DNS failure"))
    result = await RawTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.connection_error


@pytest.mark.asyncio
async def test_fetch_proxy_error_via_proxy_yields_proxy_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_session(monkeypatch, curl_exceptions.RequestException("SOCKS5 proxy refused connection"))
    result = await RawTier().fetch(
        "https://example.com/",
        state=_state(),
        proxy_url="socks5://127.0.0.1:1080",
    )
    assert result.verdict == Verdict.proxy_unavailable


@pytest.mark.asyncio
async def test_fetch_proxy_error_without_proxy_still_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A proxy-shaped error WITHOUT proxy_url is still connection_error."""
    _patch_session(monkeypatch, curl_exceptions.RequestException("SOCKS5 refused"))
    result = await RawTier().fetch("https://example.com/", state=_state(), proxy_url=None)
    assert result.verdict == Verdict.connection_error


@pytest.mark.asyncio
async def test_fetch_non_html_content_type_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    # A non-JSON non-HTML body still mismatches (escalates). JSON is carved out
    # separately (see test below).
    _patch_session(monkeypatch, _FakeResponse(content_type="application/pdf"))
    result = await RawTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.content_type_mismatch


@pytest.mark.asyncio
async def test_fetch_json_content_type_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    # json-endpoint-direct-routing: a JSON response wins at raw (Verdict.ok) so
    # the body reaches synthesis, never the jina HTML reader.
    _patch_session(monkeypatch, _FakeResponse(content_type="application/json"))
    result = await RawTier().fetch("https://api.example.com/data", state=_state())
    assert result.verdict == Verdict.ok
    assert result.content_type == "application/json"


@pytest.mark.asyncio
async def test_fetch_json_body_under_html_content_type_is_sniffed(monkeypatch: pytest.MonkeyPatch) -> None:
    # json-body-sniff: a misconfigured API serving JSON as text/html is recovered
    # — the body sniffs as JSON, so raw normalizes to application/json (ok),
    # never escalating to the jina HTML reader.
    _patch_session(monkeypatch, _FakeResponse(content_type="text/html", content=b'{"items": [{"title": "A"}]}'))
    result = await RawTier().fetch("https://api.example.com/feed", state=_state())
    assert result.verdict == Verdict.ok
    assert result.content_type == "application/json"


@pytest.mark.asyncio
async def test_fetch_real_html_is_not_sniffed_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    # A genuine HTML page never parses as JSON, so the sniff leaves it untouched.
    _patch_session(monkeypatch, _FakeResponse(content_type="text/html", content=b"<html><body>hi</body></html>"))
    result = await RawTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.ok
    assert result.content_type == "text/html"


@pytest.mark.asyncio
async def test_fetch_uses_default_ua_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await RawTier().fetch("https://example.com/", state=_state(default_ua="UA-Custom"))
    assert fake.last_request["headers"]["User-Agent"] == "UA-Custom"


@pytest.mark.asyncio
async def test_fetch_conditional_headers_included(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await RawTier().fetch(
        "https://example.com/",
        state=_state(),
        conditional_extras={"etag": '"abc"', "last_modified": "Wed, 21 Oct"},
    )
    headers = fake.last_request["headers"]
    assert headers["If-None-Match"] == '"abc"'
    assert headers["If-Modified-Since"] == "Wed, 21 Oct"


@pytest.mark.asyncio
async def test_fetch_passes_proxy_to_request(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await RawTier().fetch(
        "https://example.com/",
        state=_state(),
        proxy_url="http://proxy:8080",
    )
    assert fake.last_request["proxies"] == {"http": "http://proxy:8080", "https": "http://proxy:8080"}


@pytest.mark.asyncio
async def test_fetch_no_proxy_omits_proxies_kwarg(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_session(monkeypatch, _FakeResponse())
    await RawTier().fetch("https://example.com/", state=_state(), proxy_url=None)
    assert "proxies" not in fake.last_request
