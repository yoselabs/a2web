"""structured-data-answers — end-to-end exemption through `fetch()`.

A thin page whose answer lives in answer-bearing JSON-LD (a LocalBusiness
contact page, the Veito case) must resolve to `ok` instead of `failed`, feed
the structured rows to the `ask` extractor, and surface them in the `fetch_raw`
`content_md`. Above-floor prose keeps the legacy display pick.

Drives the real orchestrator with a mock raw tier (no network) and a stub LLM
provider (no API), mirroring `ask_response/test_fetcher_ask.py`.
"""

from __future__ import annotations

import pytest
from a2kit.testing import lazy

from a2web.fetcher import fetch
from a2web.llm_resource import LlmExtractorResource
from a2web.models import FetchStatus
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY, TierResult
from tests.conftest import make_default_state

# A thin contact page: trafilatura prose is far below the length floor, no SPA /
# anti-bot markers — a BARE length_floor without the exemption. The JSON-LD is a
# strong LocalBusiness (name/telephone/email/url = 4 populated fields).
_VEITO_CONTACT_HTML = (
    b"<html><head><title>Contact</title>"
    b'<script type="application/ld+json">'
    b'{"@context":"http://schema.org","@type":"LocalBusiness","name":"VEITO",'
    b'"telephone":"444 3 061","email":"destek@veito.com","url":"https://www.veito.com/"}'
    b"</script></head><body><p>Contact</p></body></html>"
)

# A long article body (well above the floor) that ALSO embeds a strong Product —
# the answer-bearing override must NOT fire; prose keeps the display slot.
_LONG_PROSE = "Adaptive web fetching is the practice of escalating tiers. " * 30
_ARTICLE_WITH_PRODUCT_HTML = (
    "<html><head>"
    '<script type="application/ld+json">'
    '{"@type":"Product","name":"Widget","brand":"Acme","offers":{"price":"9.99"}}'
    "</script></head><body><article><p>" + _LONG_PROSE + "</p></article></body></html>"
).encode()


class _MockTier:
    """Stand-in for the raw tier: returns a fixed body, no network."""

    name = "raw"

    def __init__(self, body: bytes) -> None:
        self._body = body

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        return TierResult(body=self._body, content_type="text/html", status_code=200, final_url=url, headers={})


def _swap_raw(monkeypatch: pytest.MonkeyPatch, body: bytes) -> None:
    monkeypatch.setitem(REGISTRY, "raw", _MockTier(body))


class _StubProvider:
    name = "stub"

    def __init__(self, *, answer: str) -> None:
        self.answer = answer
        self.calls: list[dict] = []

    async def complete(self, *, system, user, model, **_):
        self.calls.append({"system": system, "user": user, "model": model})
        from a2web.packages.llm_extract import ProviderResponse

        return ProviderResponse(text=self.answer, model=model, prompt_tokens=100, completion_tokens=10, cost_usd=0.0, latency_ms=10)


def _extractor(state: AppState, *, answer: str) -> tuple[LlmExtractorResource, _StubProvider]:
    provider = _StubProvider(answer=answer)
    return LlmExtractorResource(state.settings, state.sqlite, lazy(provider)), provider


# --------------------------------------------------------------------- #
# 5.4 — ask promotes to ok and answers from the structured menu
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_thin_localbusiness_ask_resolves_ok_and_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Veito case: thin contact page → status ok, extraction runs, and the
    structured rows (phone + email) reach the LLM."""
    _swap_raw(monkeypatch, _VEITO_CONTACT_HTML)
    state = make_default_state(settings=AppSettings())
    extractor_res, provider = _extractor(state, answer="Phone 444 3 061, email destek@veito.com")

    result = await fetch(
        "https://www.veito.com/iletisim-EN.html",
        state=state,
        ask="What is the phone and email?",
        llm_extractor=lazy(extractor_res),
    )

    assert result.status == FetchStatus.ok  # not failed — promoted by the exemption
    assert result.extracted_answer == "Phone 444 3 061, email destek@veito.com"
    assert len(provider.calls) == 1
    # The answer-bearing structured rows were in the menu handed to the LLM.
    user_payload = provider.calls[0]["user"]
    assert "444 3 061" in user_payload
    assert "destek@veito.com" in user_payload


# --------------------------------------------------------------------- #
# 5.5 — fetch_raw display surfaces the structured answer; prose override scoped
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_thin_localbusiness_fetch_raw_surfaces_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_raw (no LLM): the promoted page returns ok and content_md carries
    the structured phone + email, not the thin 'Contact' fragment."""
    _swap_raw(monkeypatch, _VEITO_CONTACT_HTML)
    state = make_default_state(settings=AppSettings())

    result = await fetch("https://www.veito.com/iletisim-EN.html", state=state)

    assert result.status == FetchStatus.ok
    assert "444 3 061" in result.content_md
    assert "destek@veito.com" in result.content_md


@pytest.mark.asyncio
async def test_above_floor_prose_keeps_display_over_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The answer-bearing display override fires ONLY for sub-floor prose — an
    above-floor article keeps its prose in content_md."""
    _swap_raw(monkeypatch, _ARTICLE_WITH_PRODUCT_HTML)
    state = make_default_state(settings=AppSettings())

    result = await fetch("https://example.org/post", state=state)

    assert result.status == FetchStatus.ok
    assert "Adaptive web fetching" in result.content_md


# --------------------------------------------------------------------- #
# structured-grounded-completeness — the promoted page is not flagged incomplete
# --------------------------------------------------------------------- #

from a2web.fetcher_response import build_ask_response  # noqa: E402

_ROUTER_EMPTY_OBSTACLE = (
    '{"answer": "Phone 444 3 061, email destek@veito.com", "structural_form": "product", "shape": "key-value", "obstacle": "empty"}'
)


def _no_paid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(REGISTRY, "zyte", raising=False)
    monkeypatch.delitem(REGISTRY, "firecrawl", raising=False)


@pytest.mark.asyncio
async def test_promoted_page_not_flagged_incomplete_on_empty_obstacle(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: thin LocalBusiness page promoted to ok, extractor reports a
    (false) obstacle=empty with a non-empty answer → structured_grounded set,
    and the ask projection does NOT flag retrieval_incomplete (confidence low)."""
    _swap_raw(monkeypatch, _VEITO_CONTACT_HTML)
    _no_paid(monkeypatch)
    state = make_default_state(settings=AppSettings())
    extractor_res, _ = _extractor(state, answer=_ROUTER_EMPTY_OBSTACLE)

    result = await fetch(
        "https://www.veito.com/iletisim-EN.html",
        state=state,
        ask="What is the phone and email?",
        llm_extractor=lazy(extractor_res),
    )

    assert result.status == FetchStatus.ok
    assert result.structured_grounded is True  # gate → context → response threading
    assert result.routing is not None and result.routing.obstacle == "empty"

    ask = build_ask_response(result, include_content=False, debug=False)
    assert ask.retrieval_incomplete is False
    assert "retrieval_incomplete" not in [h.code for h in ask.operator_hints]
    assert ask.confidence.value == "low"  # honest hedge retained


@pytest.mark.asyncio
async def test_promoted_page_empty_answer_still_hard_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """The carve-out does not rescue an EMPTY answer — extraction_empty hard-fails
    even on a structured-exemption-promoted page."""
    _swap_raw(monkeypatch, _VEITO_CONTACT_HTML)
    _no_paid(monkeypatch)
    state = make_default_state(settings=AppSettings())
    extractor_res, _ = _extractor(state, answer="")  # genuinely empty extraction

    result = await fetch(
        "https://www.veito.com/iletisim-EN.html",
        state=state,
        ask="What is the phone and email?",
        llm_extractor=lazy(extractor_res),
    )

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
