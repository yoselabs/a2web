"""JinaTier tests — auth header, deny-list, pre_rendered payload."""

from __future__ import annotations

import httpx
import pytest

from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState, build_state
from a2web.tiers.jina import JinaTier


def _state(**kwargs: object) -> AppState:
    return build_state(settings=AppSettings(**kwargs))


@pytest.mark.asyncio
async def test_free_tier_omits_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, dict[str, str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, text="# Hello\n\nbody")

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await JinaTier().fetch("https://example.com/", state=_state(jina_key=""))

    assert "authorization" not in {k.lower() for k in captured["headers"]}
    assert result.verdict == Verdict.ok
    assert result.pre_rendered.content_md == "# Hello\n\nbody"


@pytest.mark.asyncio
async def test_authorized_tier_sends_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, dict[str, str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, text="md")

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    await JinaTier().fetch("https://example.com/", state=_state(jina_key="secret123"))

    assert captured["headers"]["authorization"] == "Bearer secret123"


@pytest.mark.asyncio
async def test_deny_list_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Denied host must NOT issue an HTTP call."""
    called = {"hit": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["hit"] = True
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    state = _state(jina_deny_hosts=["intranet.example.com"])
    result = await JinaTier().fetch("https://wiki.intranet.example.com/page", state=state)

    assert called["hit"] is False
    assert result.skipped is True
    assert result.verdict == Verdict.other


@pytest.mark.asyncio
async def test_429_maps_to_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(429, text="rate"))
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await JinaTier().fetch("https://example.com/", state=_state())

    assert result.verdict == Verdict.rate_limited
    assert result.pre_rendered is None


@pytest.mark.asyncio
async def test_timeout_maps_to_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow", request=request)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await JinaTier().fetch("https://example.com/", state=_state())

    assert result.verdict == Verdict.timeout


@pytest.mark.asyncio
async def test_404_maps_to_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await JinaTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.not_found


@pytest.mark.asyncio
async def test_500_maps_to_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(503))
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await JinaTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.connection_error


@pytest.mark.asyncio
async def test_other_4xx_maps_to_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """403/401/410 etc — only 404 and 429 are special-cased."""
    transport = httpx.MockTransport(lambda req: httpx.Response(403))
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await JinaTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.connection_error


@pytest.mark.asyncio
async def test_proxy_error_maps_to_proxy_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ProxyError("upstream proxy refused", request=request)

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient

    def _factory(**kw: object) -> httpx.AsyncClient:
        # AsyncClient rejects `transport` + `proxy` together — drop proxy.
        kw.pop("proxy", None)
        return real_cls(transport=transport, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", _factory)

    result = await JinaTier().fetch(
        "https://example.com/",
        state=_state(),
        proxy_url="http://proxy:8080",
    )
    assert result.verdict == Verdict.proxy_unavailable


@pytest.mark.asyncio
async def test_generic_http_error_maps_to_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS failure")

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await JinaTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.connection_error


def test_is_denied_handles_url_without_hostname() -> None:
    """A pathological URL with no parseable host — defensive guard."""
    from a2web.tiers.jina import _is_denied

    assert _is_denied("not-a-url", ["example.com"]) is False
    assert _is_denied("", ["example.com"]) is False
