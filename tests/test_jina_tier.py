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
