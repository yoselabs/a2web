"""Every LLM completion is bounded — `anyllm` has no per-request timeout.

Without a bound, a provider that never returns hangs the fetch forever: the MCP
tool call never completes, and the caller gets nothing at all to act on. That is
strictly worse than a loud failure, which is the whole point of ADR-0009 — an
unfinished job must be visible, not silent.

The bound is applied by wrapping the PROVIDER, not each call site. There are
five `complete()` call sites today (extractor, judge, two bench judges, the eval
system) and the sixth would be written without a timeout — which is how the
unbounded state arose. `test_the_wrap_happens_at_the_seam` is what pins that.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from anyllm import LLMProvider, ProviderName
from anyllm.errors import AnyLLMError

from a2web.llm_resource import LLMTimeout, TimeoutProvider, select_provider, with_timeout
from a2web.settings import AppSettings
from tests._helpers.llm_doubles import DoubleArm


class _HangingProvider:
    """A provider that never returns — the failure this bound exists for.

    `OFF_CONTRACT` is the honest declaration and the narrow one: these doubles
    are handed to `with_timeout` directly to measure WHEN the wrapper gives up.
    Neither ever reaches a `query` path or sees the router contract, so router
    fidelity is not a property either one could have.
    """

    DOUBLES_ARM = DoubleArm.OFF_CONTRACT
    name = ProviderName.ANTHROPIC_API

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, **_kwargs: object) -> object:
        self.calls += 1
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    def available(self) -> bool:
        return True


class _FastProvider:
    """A provider that returns immediately. `OFF_CONTRACT` for the same reason."""

    DOUBLES_ARM = DoubleArm.OFF_CONTRACT
    name = ProviderName.ANTHROPIC_API

    async def complete(self, **_kwargs: object) -> str:
        return "done"

    def available(self) -> bool:
        return True


async def test_a_hanging_provider_is_cut_off() -> None:
    """THE regression. Pre-fix this coroutine never returned."""
    provider = with_timeout(_HangingProvider(), AppSettings(llm_timeout_s=0.2))

    started = time.monotonic()
    with pytest.raises(LLMTimeout) as caught:
        await provider.complete(user="anything")
    elapsed = time.monotonic() - started

    assert elapsed < 5, f"the bound did not apply — waited {elapsed:.1f}s"
    assert caught.value.seconds == 0.2


async def test_the_error_says_a2web_stopped_waiting() -> None:
    """Wording is load-bearing, not cosmetic.

    a2web cannot observe whether the upstream request was cancelled, whether
    the model is still generating, or whether tokens were billed. Reporting
    "the LLM timed out" asserts something it has no evidence for; the honest
    claim is that a2web stopped waiting.
    """
    provider = with_timeout(_HangingProvider(), AppSettings(llm_timeout_s=0.1))

    with pytest.raises(LLMTimeout) as caught:
        await provider.complete(user="anything")

    message = str(caught.value)
    assert "a2web stopped waiting" in message
    assert "cancel" not in message.lower(), "a2web cannot verify an upstream cancellation"


async def test_the_timeout_takes_the_existing_degrade_seam() -> None:
    """It must be an `AnyLLMError`, or it bypasses the ADR-0009 hint path.

    `Extractor.extract` and `Judge.score` already catch `AnyLLMError` and turn
    it into an empty answer plus a carried `provider_error`, which the
    orchestrator renders as an operator hint. A timeout raised as some other
    type escapes as an exception those callers have never seen — and the
    caller gets a crash instead of the honest-incompleteness envelope.

    Subclassing also keeps the package boundary intact: `packages/llm_extract/`
    must not import `a2web.llm_resource`, and with this base it does not need to.
    """
    provider = with_timeout(_HangingProvider(), AppSettings(llm_timeout_s=0.1))

    with pytest.raises(AnyLLMError) as caught:
        await provider.complete(user="anything")

    assert caught.value.retryable is True, "a timeout may genuinely succeed on retry"
    assert caught.value.hint, "the operator needs to know which knob to turn"
    assert "A2WEB_LLM_TIMEOUT_S" in caught.value.hint


async def test_a_healthy_call_is_untouched() -> None:
    """Anti-vacuity: a timeout that fires on healthy work is its own defect."""
    provider = with_timeout(_FastProvider(), AppSettings(llm_timeout_s=30))
    assert await provider.complete(user="anything") == "done"


def test_the_bound_can_be_disabled() -> None:
    """`llm_timeout_s <= 0` returns the provider unwrapped."""
    inner = _FastProvider()
    assert with_timeout(inner, AppSettings(llm_timeout_s=0)) is inner


def test_the_wrap_happens_at_the_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bound must come from provider construction, not from call sites.

    This is the structural half of the fix: `select_provider` is the one place
    a production provider is built, so every consumer — extractor, judge, the
    bench, and anything added later — receives a bounded provider without
    having to remember to ask for one.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")

    provider = select_provider(AppSettings())

    assert isinstance(provider, TimeoutProvider), f"select_provider returned an UNBOUNDED {type(provider).__name__}"
    assert isinstance(provider, LLMProvider), "the wrapper must still satisfy the provider protocol"
    assert provider.name == ProviderName.OPENAI_COMPATIBLE, "the wrapper must not mask which backend was chosen"
