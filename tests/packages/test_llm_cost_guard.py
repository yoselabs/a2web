"""a2web's binding of the shelf `anyllm.cost` guard (ADR-0016).

The guard MACHINERY — the `CostPolicy` allowlist, `with_cost_guard`, the
pre-spend assertion — lives in the shelf package `anyllm.cost` and is tested
there. What a2web must verify HERE is the binding: that a2web's three concrete
providers carry the `ProviderName` values the guard keys on, so the default
policy makes the RIGHT call for a2web's actual backends — the $20 regression
(metered Sonnet) is refused, the subscription path is allowed. If a2web ever
swapped an adapter or anyllm renamed a `ProviderName`, this catches it.
"""

from __future__ import annotations

import pytest
from anyllm import (
    DEFAULT_COST_POLICY,
    Completion,
    CostViolation,
    ProviderName,
    with_cost_guard,
)

from tests._helpers.llm_doubles import DoubleArm


class _FakeProvider:
    """anyllm-shaped provider carrying a real ProviderName, records if called."""

    DOUBLES_ARM = DoubleArm.OFF_CONTRACT

    default_model = ""

    def __init__(self, name: ProviderName) -> None:
        self.name = name
        self.called = False

    async def complete(self, **kwargs: object) -> Completion:
        self.called = True
        return Completion(text="OK", model=str(kwargs.get("model") or ""))

    def available(self) -> bool:
        return True


def test_a2web_provider_names_map_onto_policy() -> None:
    """a2web's three manifest providers resolve to these anyllm ProviderNames,
    and the default policy makes the intended subscription-vs-metered call."""
    # anthropic manifest -> AnthropicApiAdapter (metered) -> Sonnet refused.
    assert DEFAULT_COST_POLICY.permits(ProviderName.ANTHROPIC_API, "claude-sonnet-4-6") is False
    assert DEFAULT_COST_POLICY.permits(ProviderName.ANTHROPIC_API, "claude-haiku-4-5-20251001") is True
    # claude-code manifest -> ClaudeCodeSdkAdapter (subscription) -> any model.
    assert DEFAULT_COST_POLICY.permits(ProviderName.CLAUDE_CODE_SDK, "claude-sonnet-4-6") is True


async def test_guard_refuses_metered_sonnet_before_spending() -> None:
    """The $20 regression: a guarded anthropic-api provider must raise on Sonnet
    and never reach the network call."""
    inner = _FakeProvider(ProviderName.ANTHROPIC_API)
    guarded = with_cost_guard(inner)

    with pytest.raises(CostViolation):
        await guarded.complete(user="hi", model="claude-sonnet-4-6")

    assert inner.called is False


async def test_guard_allows_subscription_path() -> None:
    inner = _FakeProvider(ProviderName.CLAUDE_CODE_SDK)
    guarded = with_cost_guard(inner)

    result = await guarded.complete(user="hi", model="claude-sonnet-4-6")

    assert result.text == "OK"
    assert inner.called is True
