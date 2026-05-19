"""Errors raised by the a2web.llm module."""

from __future__ import annotations


class LLMNotAvailable(RuntimeError):
    """Raised when an LLM call is attempted but no provider can be reached.

    a2web v0.7+: `anthropic` + `claude-agent-sdk` are baseline deps, so
    "SDK missing" is no longer a cause. The remaining cases:

    1. No `ANTHROPIC_API_KEY` in env AND no Claude Code OAuth session.
    2. The selected provider's credentials are invalid or expired.

    The message always includes an actionable hint pointing to the fix.
    """
