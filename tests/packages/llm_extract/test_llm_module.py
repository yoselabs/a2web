"""v0.4 step 1: a2web.llm module scaffold tests.

Cover the bare-install boundary, the prompt template freshness, and the
Extractor + Provider primitive contract using an in-process mock provider.
Real Anthropic API calls are NOT made here — those happen in the eval suite
under a separate marker.
"""

from __future__ import annotations

import pytest

from a2web.packages.llm_extract import (
    JUDGE_V1,
    WEBFETCH_DEFAULT_V1,
    ExtractionResult,
    Extractor,
    LLMNotAvailable,
    ModelSpec,
    PromptTemplate,
    Provider,
    ProviderResponse,
)

# --------------------------------------------------------------------- #
# Mock provider — captures calls + returns canned responses
# --------------------------------------------------------------------- #


class MockProvider:
    """Provider stub: records every `complete()` call; returns canned text."""

    name = "mock"

    def __init__(
        self,
        *,
        answer: str = "mock answer",
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
        cost_usd: float = 0.001,
    ) -> None:
        self.answer = answer
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cost_usd = cost_usd
        self.calls: list[dict] = []

    def available(self) -> bool:
        return True

    async def complete(
        self,
        *,
        system,
        user,
        model,
        max_tokens=1024,
        temperature=0.0,
        thinking_disabled=True,
        parts=None,
    ) -> ProviderResponse:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "thinking_disabled": thinking_disabled,
                "parts": parts,
            }
        )
        return ProviderResponse(
            text=self.answer,
            model=model,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            cost_usd=self.cost_usd,
            latency_ms=42,
        )


def test_mock_provider_satisfies_protocol() -> None:
    """The MockProvider stub structurally conforms to the Provider Protocol."""
    p = MockProvider()
    assert isinstance(p, Provider)


# --------------------------------------------------------------------- #
# Prompt templates — frozen, well-shaped
# --------------------------------------------------------------------- #


def test_prompt_template_is_frozen() -> None:
    """PromptTemplate dataclasses are frozen — cannot be mutated at runtime."""
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        WEBFETCH_DEFAULT_V1.name = "different"  # type: ignore[misc]


def test_webfetch_default_v1_reproduces_binary_template() -> None:
    """Byte-for-byte check against research/123's Rb9 non-preapproved template.
    The exact constant strings must survive — they're the eval anchor.
    """
    rendered = WEBFETCH_DEFAULT_V1.user_template.format(content="MD", ask="What?")
    # Leading newline + "Web page content:" header (verbatim).
    assert rendered.startswith("\nWeb page content:\nMD\nWhat?\n")
    # All four guidance bullets present verbatim.
    assert "Enforce a strict 125-character maximum for quotes" in rendered
    assert "Open Source Software is ok as long as we respect the license" in rendered
    assert "You are not a lawyer" in rendered
    assert "Never produce or reproduce exact song lyrics" in rendered
    # System content is empty (matches WebFetch's iK([])).
    assert WEBFETCH_DEFAULT_V1.system == ()


def test_judge_v1_emits_strict_json_instruction() -> None:
    """The judge template must instruct STRICT JSON — no markdown fence."""
    body = JUDGE_V1.user_template
    assert "STRICT JSON ONLY" in body
    assert '"scores"' in body
    assert '"overall"' in body
    assert '"reached"' in body
    assert '"reasoning"' in body


# --------------------------------------------------------------------- #
# Extractor — runs template through provider, returns ExtractionResult
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_extractor_runs_template_through_provider() -> None:
    """Extractor.extract() builds a user message with the template, passes
    it to the provider, and returns a populated ExtractionResult."""
    provider = MockProvider(answer="Rust was designed by Graydon Hoare.")
    ex = Extractor(
        provider=provider,
        model=ModelSpec("test-model"),
        template=WEBFETCH_DEFAULT_V1,
    )

    result = await ex.extract(
        content="Graydon Hoare designed Rust in 2006 at Mozilla.",
        ask="Who designed Rust?",
    )

    assert isinstance(result, ExtractionResult)
    assert result.answer == "Rust was designed by Graydon Hoare."
    assert result.model == "test-model"
    assert result.template_name == "webfetch_default_v1"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.cost_usd == pytest.approx(0.001)
    assert result.cache_hit is False

    # Exactly one provider call, with the expected payload shape.
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["model"] == "test-model"
    assert call["thinking_disabled"] is True
    assert "Graydon Hoare designed Rust" in call["user"]
    assert "Who designed Rust?" in call["user"]
    assert call["system"] == ()


@pytest.mark.asyncio
async def test_extractor_truncates_content_past_cap() -> None:
    """Content past `max_content_chars` is truncated with a clear marker."""
    provider = MockProvider()
    ex = Extractor(
        provider=provider,
        model=ModelSpec("test-model"),
        max_content_chars=100,
    )

    long = "x" * 500
    result = await ex.extract(content=long, ask="?")

    assert result.raw == {"truncated": True}
    sent_user = provider.calls[0]["user"]
    assert "Content truncated to 100 chars" in sent_user


@pytest.mark.asyncio
async def test_extractor_passes_short_content_through_untruncated() -> None:
    provider = MockProvider()
    ex = Extractor(provider=provider, model=ModelSpec("test-model"))
    result = await ex.extract(content="short", ask="?")
    assert result.raw is None
    sent_user = provider.calls[0]["user"]
    assert "Content truncated" not in sent_user


def test_custom_template_overrides_default() -> None:
    """Caller-supplied templates flow through unchanged."""
    custom = PromptTemplate(
        name="custom_v1",
        version=1,
        user_template="{content}|{ask}",
    )
    provider = MockProvider()
    ex = Extractor(provider=provider, model=ModelSpec("m"), template=custom)
    assert ex.template is custom


# --------------------------------------------------------------------- #
# Module import posture
# --------------------------------------------------------------------- #


def test_llm_module_importable() -> None:
    """`from a2web.packages.llm_extract import Extractor, ModelSpec` MUST succeed.

    v0.7+: `anthropic` + `claude-agent-sdk` are baseline deps, so the import
    is always safe. This canary catches regressions in the module layout.
    """
    from a2web.packages.llm_extract import Extractor as E  # noqa: F401


def test_llm_not_available_is_runtime_error() -> None:
    """LLMNotAvailable inherits from RuntimeError so generic except blocks
    catch it under their usual semantics."""
    assert issubclass(LLMNotAvailable, RuntimeError)


# The Anthropic provider IMPLEMENTATION moved to the shelf (anyllm's
# `AnthropicApiAdapter`); its construction/availability behavior is anyllm's own
# test surface now. a2web's manifest-level gating (missing key → `Unavailable`)
# is covered by the manifest/selection tests.


# --------------------------------------------------------------------- #
# v0.7 link-discovery — Tier 2 next_links extension
# --------------------------------------------------------------------- #


def _provider_with_canned(answer_with_fence: str) -> MockProvider:
    return MockProvider(answer=answer_with_fence)


@pytest.mark.asyncio
async def test_extract_returns_next_links_from_fenced_json() -> None:
    """Single provider call returns both `answer` and `next_links`."""
    canned = (
        "The page mentions octopuses and cephalopods.\n\n"
        "```next_links\n"
        '[{"anchor":"Cephalopod","url":"https://en.wikipedia.org/wiki/Cephalopod",'
        '"reason":"deeper taxonomy","kind":"related"}]\n'
        "```\n"
    )
    provider = _provider_with_canned(canned)
    ex = Extractor(
        provider=provider,
        model=ModelSpec("mock-1"),
        template=WEBFETCH_DEFAULT_V1,
    )
    md = "content with link [x](https://en.wikipedia.org/wiki/Cephalopod)"
    result = await ex.extract(content=md, ask="what?", request_next_links=True)
    assert len(provider.calls) == 1, "Single provider call expected"
    assert "octopuses and cephalopods" in result.answer
    assert "```next_links" not in result.answer, "Fence must be stripped from answer"
    assert len(result.next_links) == 1
    assert result.next_links[0].anchor == "Cephalopod"
    assert result.next_links[0].kind == "related"


@pytest.mark.asyncio
async def test_extract_handles_missing_fence_gracefully() -> None:
    """Provider that ignores the next_links instruction → empty list, full text as answer."""
    provider = _provider_with_canned("plain answer with no fence")
    ex = Extractor(provider=provider, model=ModelSpec("m"), template=WEBFETCH_DEFAULT_V1)
    result = await ex.extract(content="c", ask="q", request_next_links=True)
    assert result.answer == "plain answer with no fence"
    assert result.next_links == []


@pytest.mark.asyncio
async def test_extract_drops_unknown_kinds() -> None:
    """Entries with invalid `kind` are silently dropped at parse time."""
    canned = (
        "answer.\n\n```next_links\n"
        '[{"anchor":"x","url":"https://e.com/a","reason":"r","kind":"bogus"},'
        '{"anchor":"y","url":"https://e.com/b","reason":"r","kind":"drilldown"}]\n```'
    )
    provider = _provider_with_canned(canned)
    ex = Extractor(provider=provider, model=ModelSpec("m"), template=WEBFETCH_DEFAULT_V1)
    result = await ex.extract(content="c", ask="q", request_next_links=True)
    assert len(result.next_links) == 1
    assert result.next_links[0].kind == "drilldown"


@pytest.mark.asyncio
async def test_extract_handler_candidates_appear_in_prompt() -> None:
    """When `handler_candidates` is non-empty, the prompt cites them for re-ranking."""
    from a2web.packages.llm_extract import LlmNextLink

    provider = _provider_with_canned("a")
    ex = Extractor(provider=provider, model=ModelSpec("m"), template=WEBFETCH_DEFAULT_V1)
    handler = [
        LlmNextLink(anchor="Top post", url="https://r/x/1", reason="100 score", kind="drilldown"),
    ]
    await ex.extract(content="c", ask="q", request_next_links=True, handler_candidates=handler)
    assert len(provider.calls) == 1
    user = provider.calls[0]["user"]
    assert "site handler suggests" in user.lower()
    assert "Top post" in user
    assert "https://r/x/1" in user


# --------------------------------------------------------------------- #
# Fail-loud → degrade seam (anyllm adoption)
#
# anyllm providers RAISE `AnyLLMError` on provider/API failure where a2web's
# old local providers returned an empty-text `ProviderResponse`. The Extractor
# catches it and rebuilds that empty result so the orchestrator's "empty answer
# → degrade to raw" path still fires; the error never propagates out of extract().
# --------------------------------------------------------------------- #


class _RaisingProvider:
    """Provider whose `complete()` fails loud with `AnyLLMError`."""

    name = "raising"

    def available(self) -> bool:
        return True

    async def complete(self, *, system, user, model, **_: object) -> ProviderResponse:
        from anyllm import AnyLLMError

        raise AnyLLMError("boom: rate limited", retryable=True, hint="retry later")


@pytest.mark.asyncio
async def test_extract_degrades_on_anyllm_error_instead_of_raising() -> None:
    """AnyLLMError from the provider → empty-answer ExtractionResult, no raise."""
    ex = Extractor(provider=_RaisingProvider(), model=ModelSpec("m"), template=WEBFETCH_DEFAULT_V1)
    result = await ex.extract(content="page body", ask="what?")
    assert result.answer == ""
    assert result.cost_usd == 0.0
    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0
