"""v0.4 step 1: a2web.llm module scaffold tests.

Cover the bare-install boundary, the prompt template freshness, and the
Extractor + Provider primitive contract using an in-process mock provider.
Real Anthropic API calls are NOT made here — those happen in the eval suite
under a separate marker.
"""

from __future__ import annotations

import pytest

from a2web.llm import (
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

    async def complete(
        self,
        *,
        system,
        user,
        model,
        max_tokens=1024,
        temperature=0.0,
        thinking_disabled=True,
    ) -> ProviderResponse:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "thinking_disabled": thinking_disabled,
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
        model=ModelSpec("mock", "test-model"),
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
        model=ModelSpec("mock", "test-model"),
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
    ex = Extractor(provider=provider, model=ModelSpec("mock", "test-model"))
    result = await ex.extract(content="short", ask="?")
    assert result.raw is None
    sent_user = provider.calls[0]["user"]
    assert "Content truncated" not in sent_user


def test_modelspec_key_includes_both_fields() -> None:
    spec = ModelSpec("anthropic", "claude-haiku-4-5-20251001")
    assert spec.key() == "anthropic:claude-haiku-4-5-20251001"


def test_custom_template_overrides_default() -> None:
    """Caller-supplied templates flow through unchanged."""
    custom = PromptTemplate(
        name="custom_v1",
        version=1,
        user_template="{content}|{ask}",
    )
    provider = MockProvider()
    ex = Extractor(
        provider=provider, model=ModelSpec("mock", "m"), template=custom
    )
    assert ex.template is custom


# --------------------------------------------------------------------- #
# Bare-install posture: importing a2web.llm without [llm] doesn't crash
# --------------------------------------------------------------------- #


def test_llm_module_importable() -> None:
    """`from a2web.llm import Extractor, ModelSpec` MUST succeed without
    the `[llm]` extra installed. (We HAVE the extra in this test env, so
    this just asserts the import path is healthy; the no-extra case is
    covered by the LLMNotAvailable test on AnthropicProvider.)
    """
    from a2web.llm import Extractor as E  # noqa: F401


def test_llm_not_available_is_runtime_error() -> None:
    """LLMNotAvailable inherits from RuntimeError so generic except blocks
    catch it under their usual semantics."""
    assert issubclass(LLMNotAvailable, RuntimeError)


@pytest.mark.asyncio
async def test_anthropic_provider_missing_key_raises_llm_not_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No API key in env → AnthropicProvider construction raises with a
    pointer at the env var."""
    from a2web.llm.providers.anthropic import AnthropicProvider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMNotAvailable) as ei:
        AnthropicProvider()
    assert "ANTHROPIC_API_KEY" in str(ei.value)


@pytest.mark.asyncio
async def test_anthropic_provider_constructs_with_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a key present, construction succeeds (no API call made)."""
    from a2web.llm.providers.anthropic import AnthropicProvider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    provider = AnthropicProvider()
    assert provider.name == "anthropic"
