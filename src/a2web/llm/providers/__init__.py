"""Provider backends for a2web.llm.

`base.py`        — Provider Protocol + ProviderResponse dataclass.
`anthropic.py`   — Anthropic Messages API via the `anthropic` SDK
                   (requires `ANTHROPIC_API_KEY`).
`claude_code.py` — Claude Code OS-session via `claude-agent-sdk` (no
                   API key needed; uses whatever Claude Code is logged
                   into — OAuth subscription or API key).
`openrouter.py`  — lands in v0.5.
"""

from __future__ import annotations

from .base import Provider, ProviderResponse

__all__ = ["Provider", "ProviderResponse"]
