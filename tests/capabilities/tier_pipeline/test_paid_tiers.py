"""Direct unit tests for the Zyte + Firecrawl paid tiers (httpx-mocked).

Exercises the real `fetch` bodies: auth wiring, response parsing, and the
tenet-critical status→verdict mapping (401/402/403 → paid_auth_error).
"""

from __future__ import annotations

import httpx
import pytest

from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers._paid import paid_verdict_for_status
from a2web.tiers.firecrawl import FirecrawlTier
from a2web.tiers.zyte import ZyteTier
from tests.conftest import make_default_state


def _state(**kwargs: object) -> AppState:
    return make_default_state(settings=AppSettings(**kwargs))


def _mock(monkeypatch: pytest.MonkeyPatch, handler: object) -> None:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))


# --------------------------------------------------------------------- #
# status → verdict map
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("status", "verdict"),
    [
        (200, Verdict.ok),
        (401, Verdict.paid_auth_error),
        (402, Verdict.paid_auth_error),
        (403, Verdict.paid_auth_error),
        (429, Verdict.rate_limited),
        (404, Verdict.not_found),
        (500, Verdict.connection_error),
    ],
)
def test_paid_verdict_for_status(status: int, verdict: Verdict) -> None:
    assert paid_verdict_for_status(status) == verdict


# --------------------------------------------------------------------- #
# Zyte
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_zyte_success_parses_browser_html(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"url": "https://ex.com/final", "browserHtml": "<html><body><h1>Title</h1><p>Body text here.</p></body></html>"},
        )

    _mock(monkeypatch, handler)
    result = await ZyteTier().fetch("https://ex.com/", state=_state(zyte_key="zk"))

    assert result.verdict == Verdict.ok
    assert result.final_url == "https://ex.com/final"
    assert result.pre_rendered is not None
    assert "Body text here." in result.pre_rendered.content_md
    # HTTP Basic with the key as username.
    assert captured["auth"] is not None


@pytest.mark.asyncio
async def test_zyte_bad_key_maps_to_paid_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock(monkeypatch, lambda request: httpx.Response(401, json={"detail": "invalid key"}))
    result = await ZyteTier().fetch("https://ex.com/", state=_state(zyte_key="bad"))
    assert result.verdict == Verdict.paid_auth_error
    assert result.pre_rendered is None


@pytest.mark.asyncio
async def test_zyte_timeout_is_non_authoritative(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    _mock(monkeypatch, handler)
    result = await ZyteTier().fetch("https://ex.com/", state=_state(zyte_key="zk"))
    assert result.verdict == Verdict.timeout


@pytest.mark.asyncio
async def test_zyte_raw_mode_decodes_body_and_reads_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    import base64 as _b64

    captured: dict[str, object] = {}
    html = b"<html><body><div class='thing comment'>hi</div></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["request"] = _json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "url": "https://old.reddit.com/r/x/comments/1/t/?limit=500&sort=top",
                "httpResponseBody": _b64.b64encode(html).decode(),
                "httpResponseHeaders": [{"name": "Content-Type", "value": "text/html; charset=UTF-8"}],
            },
        )

    _mock(monkeypatch, handler)
    result = await ZyteTier().fetch(
        "https://old.reddit.com/r/x/comments/1/t/?limit=500&sort=top",
        state=_state(zyte_key="zk"),
        mode="httpResponseBody",
    )

    # Raw mode requests httpResponseBody, not browserHtml.
    assert captured["request"] == {
        "url": "https://old.reddit.com/r/x/comments/1/t/?limit=500&sort=top",
        "httpResponseBody": True,
    }
    assert result.verdict == Verdict.ok
    assert result.body == html
    assert result.content_type == "text/html; charset=UTF-8"
    # Raw mode does NOT pre-render — the caller parses the body.
    assert result.pre_rendered is None


@pytest.mark.asyncio
async def test_zyte_raw_mode_bad_key_still_fails_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock(monkeypatch, lambda request: httpx.Response(403, json={"detail": "forbidden"}))
    result = await ZyteTier().fetch("https://old.reddit.com/r/x/comments/1/t/", state=_state(zyte_key="bad"), mode="httpResponseBody")
    assert result.verdict == Verdict.paid_auth_error
    assert result.body == b""


@pytest.mark.asyncio
async def test_zyte_raw_mode_empty_body_is_length_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock(monkeypatch, lambda request: httpx.Response(200, json={"url": "https://ex.com/", "httpResponseBody": ""}))
    result = await ZyteTier().fetch("https://ex.com/", state=_state(zyte_key="zk"), mode="httpResponseBody")
    assert result.verdict == Verdict.length_floor
    assert result.body == b""


@pytest.mark.asyncio
async def test_zyte_default_mode_is_browser_html(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["request"] = _json.loads(request.content)
        return httpx.Response(200, json={"url": "https://ex.com/", "browserHtml": "<p>Body text here.</p>"})

    _mock(monkeypatch, handler)
    await ZyteTier().fetch("https://ex.com/", state=_state(zyte_key="zk"))
    assert captured["request"] == {"url": "https://ex.com/", "browserHtml": True}


# --------------------------------------------------------------------- #
# Firecrawl
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_firecrawl_success_parses_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"success": True, "data": {"markdown": "# Real\n\nContent.", "metadata": {"sourceURL": "https://ex.com/x"}}},
        )

    _mock(monkeypatch, handler)
    result = await FirecrawlTier().fetch("https://ex.com/", state=_state(firecrawl_key="fk"))

    assert result.verdict == Verdict.ok
    assert result.final_url == "https://ex.com/x"
    assert result.pre_rendered is not None
    assert result.pre_rendered.content_md == "# Real\n\nContent."
    assert captured["auth"] == "Bearer fk"


@pytest.mark.asyncio
async def test_firecrawl_bad_key_maps_to_paid_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock(monkeypatch, lambda request: httpx.Response(402, json={"error": "payment required"}))
    result = await FirecrawlTier().fetch("https://ex.com/", state=_state(firecrawl_key="bad"))
    assert result.verdict == Verdict.paid_auth_error
    assert result.pre_rendered is None


@pytest.mark.asyncio
async def test_firecrawl_empty_markdown_is_length_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock(monkeypatch, lambda request: httpx.Response(200, json={"success": True, "data": {"markdown": ""}}))
    result = await FirecrawlTier().fetch("https://ex.com/", state=_state(firecrawl_key="fk"))
    assert result.verdict == Verdict.length_floor
    assert result.pre_rendered is None
