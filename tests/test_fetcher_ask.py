"""v0.4: end-to-end `ask=` wire-up through fetcher.

Uses a mock LLM extractor injected directly on the AppState, so no real API
calls are made. Verifies:
- `ask=` unset → extracted_answer / extraction stay None; LLM module is
  never invoked.
- `ask=` set with a working extractor → extracted_answer + extraction
  populated; full pipeline still runs.
- `ask=` set on a failed fetch → extraction skipped (no content to extract).
- `ask=` set with no LLM available → fetch still succeeds; operator hint
  surfaces the actionable reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from a2web.fetcher import fetch
from a2web.models import FetchStatus
from a2web.packages.llm_extract import Extractor, ModelSpec
from a2web.settings import AppSettings
from a2web.state import AppState, build_state
from a2web.tiers import REGISTRY, TierResult

_FIX = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------- #
# Test helpers — minimal state + mocks
# --------------------------------------------------------------------- #


class _MockTier:
    """Stand-in for the raw tier: returns a fixed body, no network."""

    name = "raw"

    def __init__(self, body: bytes) -> None:
        self._body = body

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        return TierResult(
            body=self._body,
            content_type="text/html",
            status_code=200,
            final_url=url,
            headers={"etag": '"v1"'},
        )


def _swap_raw(monkeypatch: pytest.MonkeyPatch, body: bytes) -> None:
    monkeypatch.setitem(REGISTRY, "raw", _MockTier(body))


def _make_state(**overrides) -> AppState:
    s = AppSettings(**overrides)
    return build_state(settings=s)


class _StubProvider:
    """Provider that returns a canned answer regardless of input."""

    name = "stub"

    def __init__(self, *, answer: str) -> None:
        self.answer = answer
        self.calls: list[dict] = []

    async def complete(self, *, system, user, model, **_):
        self.calls.append({"system": system, "user": user, "model": model})
        from a2web.packages.llm_extract import ProviderResponse

        return ProviderResponse(
            text=self.answer,
            model=model,
            prompt_tokens=200,
            completion_tokens=20,
            cost_usd=0.0005,
            latency_ms=120,
        )


def _inject_extractor(state: AppState, *, answer: str) -> _StubProvider:
    """Bypass LlmExtractorResource._build by seeding the inner Extractor."""
    provider = _StubProvider(answer=answer)
    state.llm_extractor._extractor = Extractor(
        provider=provider,
        model=ModelSpec("stub", "stub-model"),
    )
    return provider


# --------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_unset_does_not_invoke_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default fetch (no ask=) keeps extracted_answer/extraction as None and
    never touches the LLM module."""
    body = (_FIX / "blog.html").read_bytes()
    _swap_raw(monkeypatch, body)

    state = _make_state()
    # Even if an extractor is configured, it must not be called when ask is None.
    provider = _inject_extractor(state, answer="should not be called")

    result = await fetch("https://example.org/post", state=state)

    assert result.status == FetchStatus.ok
    assert result.extracted_answer is None
    assert result.extraction is None
    assert len(provider.calls) == 0


@pytest.mark.asyncio
async def test_ask_set_populates_extracted_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ask=... with a working extractor populates extracted_answer +
    extraction metadata; content_md is passed to the LLM."""
    body = (_FIX / "blog.html").read_bytes()
    _swap_raw(monkeypatch, body)

    state = _make_state()
    provider = _inject_extractor(state, answer="The article is about adaptive web fetching.")

    result = await fetch(
        "https://example.org/post",
        state=state,
        ask="What is this article about?",
    )

    assert result.status == FetchStatus.ok
    assert result.extracted_answer == "The article is about adaptive web fetching."
    assert result.extraction is not None
    assert result.extraction.model == "stub-model"
    assert result.extraction.prompt_tokens == 200
    assert result.extraction.completion_tokens == 20
    assert result.extraction.cost_usd == pytest.approx(0.0005)
    assert result.extraction.cache_hit is False
    # Provider received the content + ask.
    assert len(provider.calls) == 1
    user_payload = provider.calls[0]["user"]
    assert "What is this article about?" in user_payload
    # The fetched content (or the WebFetch prompt template) is in there.
    assert "Web page content:" in user_payload


@pytest.mark.asyncio
async def test_ask_skipped_on_failed_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the fetch itself fails, the LLM extractor is not invoked."""
    body = (_FIX / "cloudflare_block.html").read_bytes()
    _swap_raw(monkeypatch, body)

    state = _make_state()
    provider = _inject_extractor(state, answer="should not be called")

    result = await fetch("https://blocked.example/page", state=state, ask="anything")

    assert result.status == FetchStatus.failed
    assert result.extracted_answer is None
    assert result.extraction is None
    assert len(provider.calls) == 0


@pytest.mark.asyncio
async def test_ask_without_llm_available_records_operator_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No extractor available → fetch still succeeds; operator_hints
    contains a code=llm_unavailable entry with an actionable message."""
    body = (_FIX / "blog.html").read_bytes()
    _swap_raw(monkeypatch, body)

    state = _make_state()
    # Pre-set unavailable reason — simulates LlmExtractorResource._build's
    # failure path (missing extra OR missing API key).
    state.llm_extractor._unavailable_reason = "No Anthropic API key found."

    result = await fetch(
        "https://example.org/post",
        state=state,
        ask="What is this article about?",
    )

    assert result.status == FetchStatus.ok
    assert result.extracted_answer is None
    assert result.extraction is None
    codes = [h.code for h in result.operator_hints]
    assert "llm_unavailable" in codes
    msg = next(h for h in result.operator_hints if h.code == "llm_unavailable").message
    assert "API key" in msg
