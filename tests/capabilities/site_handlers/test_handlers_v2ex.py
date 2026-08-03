"""V2EX handler tests — API v1 topic + linear replies, URL matching."""

from __future__ import annotations

from typing import Any

import pytest

from a2web.handlers import V2EXHandler, match_handler
from a2web.handlers._common import UNRETRIEVED_MARKER
from a2web.handlers.v2ex import _topic_id
from a2web.models import Verdict
from a2web.state import AppState
from tests._helpers.fake_http import FakeCurlResp, patch_curl_session
from tests.conftest import make_default_state
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


def _state() -> AppState:
    return make_default_state()


def _responder(
    *,
    topic_status: int = 200,
    replies_status: int = 200,
    topic_empty: bool = False,
    no_replies: bool = False,
):
    """Build a fake `httpx.AsyncClient.get` routing on the endpoint path."""
    topic = "[]" if topic_empty else (_FIX / "v2ex_topic.json").read_text()
    replies = "[]" if no_replies else (_FIX / "v2ex_replies.json").read_text()

    async def _fake_get(self: Any, url: str, **kwargs: Any) -> FakeCurlResp:
        if "replies/show" in url:
            return FakeCurlResp(replies_status, text=replies if replies_status == 200 else "")
        return FakeCurlResp(topic_status, text=topic if topic_status == 200 else "")

    return _fake_get


# --------------------------------------------------------------------- #
# URL matching
# --------------------------------------------------------------------- #


def test_match_handler_returns_v2ex() -> None:
    assert isinstance(match_handler("https://www.v2ex.com/t/12345"), V2EXHandler)


def test_v2ex_matches_topic_urls() -> None:
    h = V2EXHandler()
    assert h.matches("https://www.v2ex.com/t/12345")
    assert h.matches("https://v2ex.com/t/12345")
    assert h.matches("https://www.v2ex.com/t/12345/some-slug")


def test_v2ex_does_not_match_non_topic_urls() -> None:
    assert not V2EXHandler().matches("https://www.v2ex.com/")
    assert not V2EXHandler().matches("https://www.v2ex.com/go/create")
    assert not V2EXHandler().matches("https://example.com/t/12345")
    assert match_handler("https://example.com/t/12345") is None


def test_topic_id_extraction() -> None:
    assert _topic_id("https://www.v2ex.com/t/12345") == "12345"
    assert _topic_id("https://v2ex.com/t/777/slug-here") == "777"
    assert _topic_id("https://example.com/t/1") is None


# --------------------------------------------------------------------- #
# fetch()
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_topic_url_renders_body_and_flat_replies(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_curl_session(monkeypatch, _responder())

    result = await V2EXHandler().fetch("https://www.v2ex.com/t/12345", state=_state())
    assert result.verdict == Verdict.ok
    pre = result.pre_rendered
    assert pre is not None
    assert pre.title == "A tool to share AI coding context across sessions"
    assert pre.byline == "pp3x325"
    assert "re-explaining who I am" in pre.content_md
    assert "## Replies (2)" in pre.content_md
    assert "**alice:**" in pre.content_md
    assert "**bob:**" in pre.content_md
    assert "CLAUDE.md file in the repo" in pre.content_md


@pytest.mark.asyncio
async def test_replies_failure_degrades_to_topic_only_AND_SAYS_SO(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed replies fetch degrades to topic-only — and DECLARES it.

    This test previously asserted `"## Replies" not in content_md`, pinning the
    section's silent disappearance in place as intended behaviour. A 500 on
    `replies/show.json` rendered byte-identically to a topic with no replies,
    so the caller could not tell "nobody replied" from "we did not ask
    successfully" — the ADR-0009 harm, held green by the assertion above.
    """
    patch_curl_session(monkeypatch, _responder(replies_status=500))

    result = await V2EXHandler().fetch("https://www.v2ex.com/t/12345", state=_state())
    assert result.verdict == Verdict.ok
    pre = result.pre_rendered
    assert pre is not None
    assert "re-explaining who I am" in pre.content_md
    # The section is PRESENT and marked, not absent.
    assert "## Replies" in pre.content_md
    assert UNRETRIEVED_MARKER in pre.content_md


@pytest.mark.asyncio
async def test_zero_replies_is_not_marked_unretrieved(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other direction — retrieved-and-empty must stay silent.

    Without this the marker could fire unconditionally and the test above would
    still pass, swapping one indistinguishable pair for another.
    """
    patch_curl_session(monkeypatch, _responder(no_replies=True))

    result = await V2EXHandler().fetch("https://www.v2ex.com/t/12345", state=_state())
    pre = result.pre_rendered
    assert pre is not None
    assert UNRETRIEVED_MARKER not in pre.content_md


@pytest.mark.asyncio
async def test_unknown_id_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_curl_session(monkeypatch, _responder(topic_empty=True))

    result = await V2EXHandler().fetch("https://www.v2ex.com/t/999999999", state=_state())
    assert result.verdict == Verdict.not_found


@pytest.mark.asyncio
async def test_topic_endpoint_non_200_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_curl_session(monkeypatch, _responder(topic_status=503))

    result = await V2EXHandler().fetch("https://www.v2ex.com/t/12345", state=_state())
    assert result.verdict == Verdict.not_found
