"""v0.4: end-to-end `ask=` wire-up through fetcher.

Uses a mock LLM extractor wrapped in a `Lazy[T]` thunk (a2kit v0.36+) and
passed directly to `fetch()`. No real API calls are made. Verifies:
- `ask=` unset → extracted_answer / extraction stay None; LLM module is
  never invoked.
- `ask=` set with a working extractor → extracted_answer + extraction
  populated; full pipeline still runs.
- `ask=` set on a failed fetch → extraction skipped (no content to extract).
- `ask=` set with no LLM available → fetch still succeeds; operator hint
  surfaces the actionable reason.
"""

from __future__ import annotations

import logging

import pytest
from a2kit.testing import lazy

from a2web.fetcher import fetch
from a2web.llm_resource import LlmExtractorResource
from a2web.models import FetchStatus
from a2web.packages.llm_extract import Provider
from a2web.settings import AppSettings
from a2web.state import AppState, unavailable_lazy
from a2web.tiers import REGISTRY, TierResult
from tests.conftest import make_default_state
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


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
    return make_default_state(settings=s)


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


def _make_extractor_resource(
    state: AppState,
    *,
    answer: str | None,
    unavailable_reason: str | None = None,
) -> tuple[LlmExtractorResource, _StubProvider | None]:
    """Construct a LlmExtractorResource around an injected provider.

    With `answer`: inject a working stub provider (the resource builds its own
    Extractor around it). Otherwise: inject an unavailable-provider stub so the
    extract seam raises ResourceUnavailable (the "no LLM" degrade path).
    """
    if answer is not None:
        provider = _StubProvider(answer=answer)
        return LlmExtractorResource(state.settings, state.sqlite, lazy(provider)), provider
    reason = unavailable_reason or "no LLM provider available"
    return LlmExtractorResource(state.settings, state.sqlite, unavailable_lazy(Provider, reason=reason)), None


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
    extractor_res, provider = _make_extractor_resource(state, answer="should not be called")

    result = await fetch(
        "https://example.org/post",
        state=state,
        llm_extractor=lazy(extractor_res),
    )

    assert result.status == FetchStatus.ok
    assert result.extracted_answer is None
    assert result.extraction is None
    assert provider is not None
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
    extractor_res, provider = _make_extractor_resource(state, answer="The article is about adaptive web fetching.")

    result = await fetch(
        "https://example.org/post",
        state=state,
        ask="What is this article about?",
        llm_extractor=lazy(extractor_res),
    )

    assert result.status == FetchStatus.ok
    assert result.extracted_answer == "The article is about adaptive web fetching."
    assert result.extraction is not None
    # The resource builds its Extractor around the injected provider using the
    # configured model id (the stub echoes it back).
    assert result.extraction.model == "claude-haiku-4-5-20251001"
    assert result.extraction.prompt_tokens == 200
    assert result.extraction.completion_tokens == 20
    assert result.extraction.cost_usd == pytest.approx(0.0005)
    assert result.extraction.cache_hit is False
    assert provider is not None
    assert len(provider.calls) == 1
    user_payload = provider.calls[0]["user"]
    assert "What is this article about?" in user_payload
    assert "Web page content:" in user_payload


@pytest.mark.asyncio
async def test_ask_empty_answer_fails_hard_with_extraction_empty_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """never-silently-miss at extraction granularity: real content fetched but
    the LLM produced an EMPTY answer → a FULL failure (status=failed +
    retrieval_incomplete), not just a hint, so an agent that branches on `status`
    can never read an empty answer as a complete one (the model-swap risk)."""
    body = (_FIX / "blog.html").read_bytes()
    _swap_raw(monkeypatch, body)

    state = _make_state()
    extractor_res, _ = _make_extractor_resource(state, answer="")  # extraction runs, yields nothing

    result = await fetch(
        "https://example.org/post",
        state=state,
        ask="What is this article about?",
        llm_extractor=lazy(extractor_res),
    )

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
    assert not (result.extracted_answer or "").strip()
    hints = [h for h in result.operator_hints if h.code == "extraction_empty"]
    assert len(hints) == 1
    assert hints[0].severity == "critical"
    # A failed envelope must carry the failure-only narrative (not the "→ ok" line).
    assert "empty answer" in result.narrative


@pytest.mark.asyncio
async def test_ask_nonempty_answer_has_no_extraction_empty_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """A populated answer must NOT trigger the empty-extraction guard."""
    body = (_FIX / "blog.html").read_bytes()
    _swap_raw(monkeypatch, body)

    state = _make_state()
    extractor_res, _ = _make_extractor_resource(state, answer="A real, substantive answer about the article.")

    result = await fetch(
        "https://example.org/post",
        state=state,
        ask="What is this article about?",
        llm_extractor=lazy(extractor_res),
    )

    assert not any(h.code == "extraction_empty" for h in result.operator_hints)


@pytest.mark.asyncio
async def test_ask_skipped_on_failed_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the fetch itself fails, the LLM extractor is not invoked."""
    body = (_FIX / "cloudflare_block.html").read_bytes()
    _swap_raw(monkeypatch, body)

    state = _make_state()
    extractor_res, provider = _make_extractor_resource(state, answer="should not be called")

    result = await fetch(
        "https://blocked.example/page",
        state=state,
        ask="anything",
        llm_extractor=lazy(extractor_res),
    )

    assert result.status == FetchStatus.failed
    assert result.extracted_answer is None
    assert result.extraction is None
    assert provider is not None
    assert len(provider.calls) == 0


@pytest.mark.asyncio
async def test_ask_without_llm_available_fails_hard_with_critical_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ask` with no LLM backend configured → the fetch itself succeeds, but the
    ask delivered no answer, so it fails hard (status=failed + retrieval_incomplete)
    with a CRITICAL llm_unavailable hint — a misconfigured/keyless server can't
    silently return an answerless-but-ok response. `fetch_raw` is unaffected."""
    body = (_FIX / "blog.html").read_bytes()
    _swap_raw(monkeypatch, body)

    state = _make_state()
    extractor_res, _ = _make_extractor_resource(state, answer=None, unavailable_reason="No Anthropic API key found.")

    result = await fetch(
        "https://example.org/post",
        state=state,
        ask="What is this article about?",
        llm_extractor=lazy(extractor_res),
    )

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
    assert result.extracted_answer is None
    assert result.extraction is None
    hint = next(h for h in result.operator_hints if h.code == "llm_unavailable")
    assert hint.severity == "critical"
    assert "API key" in hint.message


# --------------------------------------------------------------------- #
# Provider failure vs. genuine empty answer
#
# Both leave `answer == ""` over real content, so before this split they were
# indistinguishable on the wire and BOTH got `extraction_empty`'s advice —
# "retry, use fetch_raw, or rephrase the question". That advice is actively
# wrong for a broken backend: it sends the operator to inspect page content and
# reword prompts for what is a credentials/availability problem.
# --------------------------------------------------------------------- #


class _ErroringProvider:
    """Provider whose `complete()` raises, as anyllm backends do on failure."""

    name = "stub"

    def __init__(self, *, message: str, retryable: bool = False) -> None:
        self.message = message
        self.retryable = retryable
        self.calls: list[dict] = []

    async def complete(self, *, system, user, model, **_):
        self.calls.append({"model": model})
        from anyllm import AnyLLMError

        raise AnyLLMError(self.message, retryable=self.retryable)


def _make_erroring_extractor(state: AppState, *, message: str, retryable: bool = False) -> LlmExtractorResource:
    provider = _ErroringProvider(message=message, retryable=retryable)
    return LlmExtractorResource(state.settings, state.sqlite, lazy(provider))


@pytest.mark.asyncio
async def test_provider_error_surfaces_llm_error_not_extraction_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed provider call must name the backend, never blame the page."""
    _swap_raw(monkeypatch, (_FIX / "blog.html").read_bytes())
    state = _make_state()

    result = await fetch(
        "https://example.org/post",
        state=state,
        ask="What is this article about?",
        llm_extractor=lazy(_make_erroring_extractor(state, message="401 invalid api key")),
    )

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
    codes = [h.code for h in result.operator_hints]
    assert "llm_error" in codes
    assert "extraction_empty" not in codes  # exactly one story, never both
    hint = next(h for h in result.operator_hints if h.code == "llm_error")
    assert hint.severity == "critical"
    assert "401 invalid api key" in hint.message  # the cause survives to the caller
    assert "Retrying will not help" in hint.fix  # non-retryable → honest advice
    assert "extraction provider errored" in result.narrative


@pytest.mark.asyncio
async def test_retryable_provider_error_says_retry_may_help(monkeypatch: pytest.MonkeyPatch) -> None:
    """anyllm classifies transience; the hint must not flatten that away."""
    _swap_raw(monkeypatch, (_FIX / "blog.html").read_bytes())
    state = _make_state()

    result = await fetch(
        "https://example.org/post",
        state=state,
        ask="What is this article about?",
        llm_extractor=lazy(_make_erroring_extractor(state, message="529 overloaded", retryable=True)),
    )

    hint = next(h for h in result.operator_hints if h.code == "llm_error")
    assert "transient" in hint.fix
    assert "Retrying will not help" not in hint.fix


@pytest.mark.asyncio
async def test_genuine_empty_answer_still_gets_extraction_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mirror: no provider error → the original story is unchanged."""
    _swap_raw(monkeypatch, (_FIX / "blog.html").read_bytes())
    state = _make_state()
    extractor_res, _ = _make_extractor_resource(state, answer="")

    result = await fetch(
        "https://example.org/post",
        state=state,
        ask="What is this article about?",
        llm_extractor=lazy(extractor_res),
    )

    codes = [h.code for h in result.operator_hints]
    assert "extraction_empty" in codes
    assert "llm_error" not in codes


@pytest.mark.asyncio
async def test_provider_error_is_logged(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    """A live extraction outage must leave a trace — it previously left none."""
    _swap_raw(monkeypatch, (_FIX / "blog.html").read_bytes())
    state = _make_state()

    with caplog.at_level(logging.WARNING, logger="a2kit"):
        await fetch(
            "https://example.org/post",
            state=state,
            ask="What is this article about?",
            llm_extractor=lazy(_make_erroring_extractor(state, message="401 invalid api key")),
        )

    assert any(r.getMessage() == "llm_provider_error" for r in caplog.records)
