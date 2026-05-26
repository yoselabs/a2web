"""Claude Code provider manifest — piggybacks on the OS session via
`claude-agent-sdk`. Returns Unavailable when the CLI isn't logged in."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.packages.llm_extract import LLMNotAvailable, Provider
from a2web.packages.llm_extract.providers.claude_code import ClaudeCodeProvider
from a2web.settings import AppSettings


def _build(_settings: AppSettings) -> Provider | Unavailable:
    try:
        return ClaudeCodeProvider()
    except LLMNotAvailable as exc:
        return Unavailable(str(exc))


MANIFEST = PluginManifest(
    name="claude-code",
    protocol=Provider,
    factory=_build,
)
