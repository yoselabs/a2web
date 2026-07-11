"""Unit tests for the llm-cost-guard primitive.

Asserts the default policy's allow/deny decisions and that the guarded
provider raises BEFORE issuing the underlying `complete()` call — the
structural "impossible to bill by accident" guarantee (ADR-0016).
"""

from __future__ import annotations

import pytest

from a2web.packages.llm_cost_guard import (
    DEFAULT_POLICY,
    CostViolation,
    assert_within_budget,
    with_cost_guard,
)


class _FakeProvider:
    """Minimal anyllm-shaped LLMProvider that records whether it was called."""

    name = "fake"
    default_model = ""

    def __init__(self) -> None:
        self.called = False

    async def complete(self, **kwargs: object) -> str:
        self.called = True
        return "OK"

    def available(self) -> bool:
        return True


@pytest.mark.parametrize(
    ("provider_id", "model", "allowed"),
    [
        # claude-code (subscription, flat cost) — any model is fine.
        ("claude-code", "claude-sonnet-4-6", True),
        ("claude-code", "claude-opus-4-8", True),
        ("claude-code", "claude-haiku-4-5-20251001", True),
        # metered anthropic — cheap models only.
        ("anthropic", "claude-haiku-4-5-20251001", True),
        ("anthropic", "claude-sonnet-4-6", False),  # the $20 case
        ("anthropic", "claude-opus-4-8", False),
        # openai_compatible — conservative cheap allowlist, expensive denied.
        ("openai_compatible", "gpt-4o-mini", True),
        ("openai_compatible", "llama-3.1-8b-instruct", True),
        ("openai_compatible", "gpt-4o", False),
        ("openai_compatible", "gpt-4-turbo", False),
        # unknown provider id — denied (fail loud, opt in deliberately).
        ("mystery-provider", "some-cheap-model", False),
    ],
)
def test_default_policy_allow_deny(provider_id: str, model: str, allowed: bool) -> None:
    assert DEFAULT_POLICY.permits(provider_id, model) is allowed
    if allowed:
        assert_within_budget(provider_id, model)  # no raise
    else:
        with pytest.raises(CostViolation):
            assert_within_budget(provider_id, model)


async def test_guard_raises_before_calling_inner() -> None:
    """A denied pair raises CostViolation and the inner provider is never called."""
    inner = _FakeProvider()
    guarded = with_cost_guard("anthropic", inner)  # type: ignore[arg-type]

    with pytest.raises(CostViolation):
        await guarded.complete(user="hi", model="claude-sonnet-4-6")

    assert inner.called is False, "denied pair must not reach the network call"


async def test_guard_delegates_on_allowed_pair() -> None:
    inner = _FakeProvider()
    guarded = with_cost_guard("claude-code", inner)  # type: ignore[arg-type]

    result = await guarded.complete(user="hi", model="claude-sonnet-4-6")

    assert result == "OK"
    assert inner.called is True


async def test_guard_forwards_attributes_and_available() -> None:
    inner = _FakeProvider()
    inner.default_model = "claude-haiku-4-5-20251001"
    guarded = with_cost_guard("anthropic", inner)  # type: ignore[arg-type]

    # default_model forwarded through __getattr__; available() delegated.
    assert guarded.default_model == "claude-haiku-4-5-20251001"  # type: ignore[attr-defined]
    assert guarded.available() is True

    # With no explicit model, the inner default_model is what gets asserted —
    # haiku is allowed on anthropic, so the call goes through.
    assert await guarded.complete(user="hi") == "OK"
    assert inner.called is True
