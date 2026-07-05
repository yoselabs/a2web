"""HN Algolia search-UI handler — hn.algolia.com/?q= routes via the search API.

search-retrieval-and-confabulation-guard P3: the Algolia search SPA URL is
claimed by HNHandler and resolved through /api/v1/search rather than rendered
as a client-side SPA shell.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from a2web.handlers import HNHandler, match_handler
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from tests._helpers.fake_http import FakeCurlResp, patch_curl_session
from tests.conftest import make_default_state
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR
_SEARCH_PAYLOAD = (_FIX / "hn_front_page.json").read_text()  # Algolia search hits share the front-page shape


def _state() -> AppState:
    return make_default_state()


def _settings() -> AppSettings:
    return make_default_state().settings


# --------------------------------------------------------------------- #
# matches() — the Algolia search-UI shape
# --------------------------------------------------------------------- #


def test_matches_algolia_search_url() -> None:
    assert HNHandler().matches("https://hn.algolia.com/?q=claude%20code")


def test_match_handler_routes_algolia_search_to_hn() -> None:
    h = match_handler("https://hn.algolia.com/?q=claude%20code", _settings())
    assert isinstance(h, HNHandler)


def test_does_not_match_algolia_without_query() -> None:
    assert not HNHandler().matches("https://hn.algolia.com/")


def test_still_matches_ycombinator_front_page_and_item() -> None:
    h = HNHandler()
    assert h.matches("https://news.ycombinator.com/")
    assert h.matches("https://news.ycombinator.com/item?id=123")


# --------------------------------------------------------------------- #
# fetch() — routes to the Algolia search API
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_search_url_calls_algolia_search_api(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = patch_curl_session(
        monkeypatch,
        lambda self, url, **kw: FakeCurlResp(200, text=_SEARCH_PAYLOAD, headers={"content-type": "application/json"}),
    )

    result = await HNHandler().fetch("https://hn.algolia.com/?q=claude%20code", state=_state())

    called = urlparse(fake.last_request["url"])
    assert called.hostname == "hn.algolia.com"
    assert called.path == "/api/v1/search"
    q = parse_qs(called.query)
    assert q.get("query") == ["claude code"]
    assert q.get("tags") == ["story"]
    assert q.get("hitsPerPage") == ["30"]

    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.content_md.strip()
    assert len(result.next_links) > 0


@pytest.mark.asyncio
async def test_search_upstream_error_surfaces_non_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_curl_session(
        monkeypatch,
        lambda self, url, **kw: FakeCurlResp(503, text="upstream down", headers={"content-type": "text/plain"}),
    )

    result = await HNHandler().fetch("https://hn.algolia.com/?q=claude", state=_state())
    assert result.verdict != Verdict.ok  # centralized non-OK mapping, not a silent empty success


# --------------------------------------------------------------------- #
# escalate to a paid site render on a converted-fetch failure (P4)
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_api_error_escalates_to_site_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the rewritten Algolia API fails, the handler signals a direct site
    render so the orchestrator renders the ORIGINAL url instead of surfacing the
    API error (and instead of dead-ending on the free-tier SPA shell)."""
    patch_curl_session(
        monkeypatch,
        lambda self, url, **kw: FakeCurlResp(503, text="upstream down", headers={"content-type": "text/plain"}),
    )
    result = await HNHandler().fetch("https://hn.algolia.com/?q=claude", state=_state())
    assert result.escalate_to_render is True


@pytest.mark.asyncio
async def test_unparseable_api_body_escalates_to_site_render(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_curl_session(
        monkeypatch,
        lambda self, url, **kw: FakeCurlResp(200, text="<html>not json</html>", headers={"content-type": "text/html"}),
    )
    result = await HNHandler().fetch("https://hn.algolia.com/?q=claude", state=_state())
    assert result.escalate_to_render is True


@pytest.mark.asyncio
async def test_successful_search_does_not_escalate_render(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_curl_session(
        monkeypatch,
        lambda self, url, **kw: FakeCurlResp(200, text=_SEARCH_PAYLOAD, headers={"content-type": "application/json"}),
    )
    result = await HNHandler().fetch("https://hn.algolia.com/?q=claude", state=_state())
    assert result.escalate_to_render is False
