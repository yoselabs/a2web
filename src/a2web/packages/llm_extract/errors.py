"""Errors raised by the a2web.llm module."""

from __future__ import annotations

from a2effect.errors import AuthError


class LLMNotAvailable(AuthError, RuntimeError):
    """Raised when an LLM call is attempted but no provider can be reached.

    a2web v0.7+: `anthropic` + `claude-agent-sdk` are baseline deps, so
    "SDK missing" is no longer a cause. The remaining cases:

    1. No `ANTHROPIC_API_KEY` in env AND no Claude Code OAuth session.
    2. The selected provider's credentials are invalid or expired.

    The message always includes an actionable hint pointing to the fix.

    **`AuthError`, so `guard_tool`'s typed branch can see it.** Both causes
    above are credential problems, which is that class exactly ("authentication
    is required or failed"). NOT `InfrastructureError` — that class is defined
    as retryable, and retrying a missing key never helps. Until 2026-07-31
    a2web raised none of `a2effect`'s five types, so `except AppError` in
    `guard_tool` was unreachable and this rendered as `UnexpectedDefect`: a
    missing credential and a null deref reached the caller identically.

    `RuntimeError` is kept in the bases deliberately. Every existing `except`
    site catches it as one, and dropping it would turn handled degradations
    into crashes — a silent scope change riding along with a cosmetic retype.
    """

    kind = "auth"
