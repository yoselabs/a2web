"""Eager Reddit → Zyte old.reddit routing + content-expectations (reddit-via-zyte).

Mocks the Zyte HTTP call (httpx) and drives `RedditHandler.fetch` end to end:
a keyed thread returns a scored/nested sample with measured comment counts and
an honest `comments_partial` hint; a bad key fails loud; the `privacy` policy
and un-keyed deployments skip Zyte. Plus unit tests for the pure `assess` seam.
"""

from __future__ import annotations

import base64
from pathlib import Path

import httpx
import pytest

from a2web import content_expectations
from a2web.handlers import RedditHandler
from a2web.handlers.reddit import _zyte_reddit_enabled
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from tests.conftest import make_default_state

_FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "reddit" / "oldreddit_thread.html"
_THREAD_URL = "https://www.reddit.com/r/science/comments/abc123/why_pushups/"


def _state(**kwargs: object) -> AppState:
    return make_default_state(settings=AppSettings(**kwargs))


def _mock_zyte(monkeypatch: pytest.MonkeyPatch, response: httpx.Response, captured: dict[str, object] | None = None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            import json as _json

            captured["request"] = _json.loads(request.content)
        return response

    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))


def _zyte_ok_body(html: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "url": "https://old.reddit.com/r/science/comments/abc123/why_pushups/?limit=500&sort=top",
            "httpResponseBody": base64.b64encode(html.encode()).decode(),
            "httpResponseHeaders": [{"name": "Content-Type", "value": "text/html"}],
        },
    )


# --------------------------------------------------------------------- #
# Policy gating
# --------------------------------------------------------------------- #


def test_zyte_reddit_enabled_requires_key_and_robustness() -> None:
    assert _zyte_reddit_enabled(_state(zyte_key="zk")) is True
    assert _zyte_reddit_enabled(_state()) is False  # un-keyed
    assert _zyte_reddit_enabled(_state(zyte_key="zk", reddit_tier_policy="privacy")) is False


# --------------------------------------------------------------------- #
# Eager path
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_thread_routes_to_zyte_old_reddit_with_scored_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    _mock_zyte(monkeypatch, _zyte_ok_body(_FIXTURE.read_text()), captured)

    result = await RedditHandler().fetch(_THREAD_URL, state=_state(zyte_key="zk"))

    # Fetched old.reddit ?limit=500&sort=top in raw (httpResponseBody) mode.
    assert captured["request"] == {
        "url": "https://old.reddit.com/r/science/comments/abc123/why_pushups/?limit=500&sort=top",
        "httpResponseBody": True,
    }
    assert result.verdict == Verdict.ok
    assert result.final_url.startswith("https://old.reddit.com/")
    assert result.pre_rendered is not None
    assert "u/alice (312 points)" in result.pre_rendered.content_md
    # Measured counts threaded onto the tier result.
    assert result.comments_loaded == 3
    assert result.comments_total == 458


@pytest.mark.asyncio
async def test_deep_thread_emits_comments_partial_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_zyte(monkeypatch, _zyte_ok_body(_FIXTURE.read_text()))
    result = await RedditHandler().fetch(_THREAD_URL, state=_state(zyte_key="zk"))

    assert result.operator_hint is not None
    assert result.operator_hint.code == "comments_partial"
    assert result.operator_hint.severity == "info"
    assert "3 of 458" in result.operator_hint.message


@pytest.mark.asyncio
async def test_bad_zyte_key_fails_loud_no_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_zyte(monkeypatch, httpx.Response(403, json={"detail": "forbidden"}))
    result = await RedditHandler().fetch(_THREAD_URL, state=_state(zyte_key="bad"))
    # Authoritative paid_auth_error — never a silent fall-through to RSS.
    assert result.verdict == Verdict.paid_auth_error


@pytest.mark.asyncio
async def test_zyte_transient_failure_falls_through_to_rss(monkeypatch: pytest.MonkeyPatch) -> None:
    # Zyte times out → None → the handler drops to the keyless RSS channel,
    # which (unmocked curl) returns a non-ok verdict. The key assertion is that
    # we did NOT fail loud with paid_auth_error and did NOT crash.
    def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    transport = httpx.MockTransport(raise_timeout)
    real_cls = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_cls(transport=transport, **kw))

    result = await RedditHandler().fetch(_THREAD_URL, state=_state(zyte_key="zk"))
    assert result.verdict is not Verdict.paid_auth_error


# --------------------------------------------------------------------- #
# content_expectations.assess()
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("loaded", "total", "expected"),
    [
        (458, 32346, "partial"),  # deep thread past the limit → labeled sample
        (30, 30, "ready"),  # small thread fully loaded
        (28, 30, "ready"),  # within tolerance
        (10, 500, "partial"),  # well short of the reachable target
        (0, 128, "fail"),  # oracle positive, nothing parsed → never-silently-miss
        (0, 0, "ready"),  # genuinely empty thread
        (5, None, "ready"),  # no oracle → default readiness
    ],
)
def test_assess_readiness(loaded: int, total: int | None, expected: str) -> None:
    assert content_expectations.assess(loaded=loaded, total=total) == expected


# --------------------------------------------------------------------- #
# End-to-end: the envelope surfaces the counts + hint through the orchestrator
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fetch_surfaces_comment_counts_and_partial_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    from a2web.fetcher import fetch

    _mock_zyte(monkeypatch, _zyte_ok_body(_FIXTURE.read_text()))
    result = await fetch(_THREAD_URL, state=_state(zyte_key="zk"))

    assert result.comments_loaded == 3
    assert result.comments_total == 458
    assert any(h.code == "comments_partial" for h in result.operator_hints)
    assert "u/alice (312 points)" in result.content_md
    # Additive + omit-when-empty: a normal (non-reddit) success carries neither
    # field on the wire; here they ARE present.
    dumped = result.model_dump()
    assert dumped.get("comments_total") == 458
