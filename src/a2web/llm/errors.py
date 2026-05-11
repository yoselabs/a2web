"""Errors raised by the a2web.llm module."""

from __future__ import annotations


class LLMNotAvailable(RuntimeError):
    """Raised when an LLM call is attempted but the backing SDK is unavailable.

    Two common causes:
    1. The `[llm]` extra was not installed (`pip install a2web[llm]`).
    2. The required API key is not set in the environment.

    The message always includes an actionable hint pointing to the fix.
    """
