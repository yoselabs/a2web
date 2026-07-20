"""llm-cost-guard — refuse expensive model spend before the call is issued.

Substrate-indifferent primitive (no a2web domain imports): wraps an anyllm
``LLMProvider`` so every ``complete()`` asserts the resolved
``(provider_id, model)`` pair against a :class:`CostPolicy` **before** the
network call. The dev/eval loop obtains its provider only pre-wrapped, so no
un-guarded completion path exists (ADR-0016 — structural prevention, not
vigilance).

Rule: *expensive models only via subscription, never metered.* The default
policy allows ``claude-code`` (flat subscription) with any model, metered
``anthropic`` with cheap models only, ``openai_compatible`` with a cheap
allowlist, and DENIES everything else — an unknown pair fails loud so a new
model is opted in deliberately, never billed by accident.

Shelf-bound: promote to ``llm-cost-guard`` on the shelf once a second project
consumes it (rule-of-three). Until then it lives here, importing only anyllm +
stdlib so it stays domain-independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from anyllm import Completion, LLMProvider, PromptParts, ProviderName


class CostViolation(RuntimeError):
    """Raised when a ``(provider_id, model)`` pair is not cheap-approved."""


@dataclass(frozen=True, slots=True)
class CostPolicy:
    """Per-provider allow-globs over lowercased model ids.

    Stored as a tuple of ``(provider_id, patterns)`` pairs (not a dict) so the
    policy stays a frozen, hashable, immutable boundary value. A provider id
    absent from the table is DENIED — the safe default (fail loud, opt in
    deliberately).
    """

    allow: tuple[tuple[str, tuple[str, ...]], ...]

    def permits(self, provider_id: str, model: str) -> bool:
        m = (model or "").lower()
        for pid, patterns in self.allow:
            if pid == provider_id:
                return any(fnmatch(m, p) for p in patterns)
        return False


# Default policy — encodes "expensive models only via subscription, never
# metered". claude-code is flat-cost (subscription) so any model is fine
# (the Sonnet judge is free there); metered anthropic is cheap-models-only;
# openai_compatible (last-resort, only when explicitly configured) allows a
# conservative cheap allowlist and denies everything else — so an unrecognised
# OpenAI model is refused (fail loud) rather than billed.
DEFAULT_POLICY = CostPolicy(
    allow=(
        ("claude-code", ("*",)),
        ("anthropic", ("*haiku*",)),
        ("openai_compatible", ("*mini*", "*nano*", "*flash*", "*small*", "*7b*", "*8b*", "*haiku*")),
    )
)


def assert_within_budget(provider_id: str, model: str, policy: CostPolicy = DEFAULT_POLICY) -> None:
    """Raise :class:`CostViolation` unless ``(provider_id, model)`` is cheap-approved."""
    if not policy.permits(provider_id, model):
        raise CostViolation(
            f"provider={provider_id!r} model={model!r} is not cheap-approved — "
            "the dev/eval loop must never bill an expensive or metered model "
            "(ADR-0016). Use the claude-code subscription, or add the pair to the "
            "CostPolicy allowlist to opt in deliberately."
        )


class _GuardedProvider:
    """anyllm ``LLMProvider`` wrapper: asserts cost, then delegates ``complete``.

    Structural (duck-typed) ``LLMProvider`` — exposes ``name`` / ``complete`` /
    ``available`` and forwards any other attribute (e.g. ``default_model``) to
    the wrapped provider.
    """

    def __init__(self, provider_id: str, inner: LLMProvider, policy: CostPolicy) -> None:
        self._provider_id = provider_id
        self._inner = inner
        self._policy = policy
        # anyllm v0.3.0 narrowed `LLMProvider.name` from `str` to the `ProviderName`
        # enum. Mirror the wrapped provider's own value so the wrapper still
        # satisfies the protocol; `provider_id` (a plain manifest string) is only
        # the fallback for a provider that exposes no name at all, and it is
        # cast because ProviderName is str-valued — comparisons against the old
        # literals still hold.
        self.name: ProviderName = getattr(inner, "name", None) or cast("ProviderName", provider_id)

    async def complete(
        self,
        *,
        user: str,
        system: tuple[str, ...] | str = (),
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        thinking_disabled: bool = True,
        parts: PromptParts | None = None,
    ) -> Completion:
        # Resolve the model the call would actually run against, then assert
        # BEFORE issuing the network call — no spend happens on a denied pair.
        effective = model or getattr(self._inner, "default_model", "") or ""
        assert_within_budget(self._provider_id, effective, self._policy)
        return await self._inner.complete(
            user=user,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking_disabled=thinking_disabled,
            parts=parts,
        )

    def available(self) -> bool:
        return self._inner.available()

    def __getattr__(self, item: str) -> Any:
        # Forward unknown attributes (default_model, etc.) to the inner
        # provider. Guarded against recursion before _inner is set.
        inner = self.__dict__.get("_inner")
        if inner is None:
            raise AttributeError(item)
        return getattr(inner, item)


def with_cost_guard(
    provider_id: str,
    provider: LLMProvider,
    policy: CostPolicy = DEFAULT_POLICY,
) -> LLMProvider:
    """Wrap ``provider`` so every ``complete()`` is cost-asserted first.

    ``provider_id`` is the stable manifest name (``claude-code`` /
    ``anthropic`` / ``openai_compatible``) that the policy keys on — not the
    anyllm ``.name`` (which can vary).
    """
    return _GuardedProvider(provider_id, provider, policy)  # type: ignore[return-value]


__all__ = [
    "DEFAULT_POLICY",
    "CostPolicy",
    "CostViolation",
    "assert_within_budget",
    "with_cost_guard",
]
