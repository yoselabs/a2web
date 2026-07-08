"""Claude Code provider manifest — piggybacks on the OS session via anyllm's
`ClaudeCodeSdkAdapter`. Returns Unavailable when `claude-agent-sdk` is absent."""

from __future__ import annotations

from anyllm import ClaudeCodeSdkAdapter

from a2web._plugin import PluginManifest, Unavailable
from a2web.packages.llm_extract import LLMNotAvailable, Provider
from a2web.settings import AppSettings


def _build(_settings: AppSettings) -> Provider | Unavailable:
    # anyllm's adapter never raises on construction — `available()` probes the SDK
    # presence via a cheap `find_spec` (no ~210MB import). Gate on it and keep
    # a2web's actionable `LLMNotAvailable` message (mapped to `Unavailable`) so the
    # SDK-absent slim container drops this rung and auto-select falls through.
    adapter = ClaudeCodeSdkAdapter()
    if not adapter.available():
        return Unavailable(
            str(
                LLMNotAvailable(
                    "claude-agent-sdk is not installed. Install the extra with "
                    "`pip install a2web[claude-code]`, or set ANTHROPIC_API_KEY / "
                    "OPENAI_API_KEY to use a different backend."
                )
            )
        )
    return adapter


MANIFEST = PluginManifest(
    name="claude-code",
    protocol=Provider,
    factory=_build,
)
