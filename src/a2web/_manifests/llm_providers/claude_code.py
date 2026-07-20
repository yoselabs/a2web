"""Claude Code provider manifest — piggybacks on the OS session via anyllm's
`ClaudeCodeSdkAdapter`. Returns Unavailable when the SDK is absent OR when no
usable Claude Code session could exist (the `claude` CLI is not on PATH)."""

from __future__ import annotations

import os
import shutil

from anyllm import ClaudeCodeSdkAdapter

from a2web._plugin import PluginManifest, Unavailable
from a2web.packages.llm_extract import LLMNotAvailable, Provider
from a2web.settings import AppSettings

# The CLI binary `claude-agent-sdk` shells out to. The SDK is a thin Python
# wrapper: with the CLI missing there is no session and every `complete()`
# yields empty text, so CLI presence is a NECESSARY condition for this rung.
_CLI = "claude"
# Escape hatch for non-standard installs (the SDK honours the same variable).
_CLI_PATH_ENV = "CLAUDE_CODE_CLI_PATH"


def _session_possible() -> bool:
    """Best-effort probe for a *usable* Claude Code session.

    Deliberately probes only for the CLI, never for credentials. Auth is
    Keychain-backed on macOS (no `~/.claude/.credentials.json`), so a
    credentials-file check would false-negative on developer machines. CLI
    presence is the cheap, portable necessary condition; a present CLI with a
    dead session still fails, but it fails LOUDLY at the extract seam rather
    than silently shadowing a configured gateway.
    """
    explicit = os.environ.get(_CLI_PATH_ENV, "").strip()
    if explicit:
        return os.path.isfile(explicit) and os.access(explicit, os.X_OK)
    return shutil.which(_CLI) is not None


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
    # SDK importable is NOT sufficient. The published image bakes the SDK in but
    # carries no `claude` CLI and no OAuth session, so this rung used to report
    # itself available, win the `auto` order, and return empty answers forever
    # while the operator's configured OPENAI_* gateway was never consulted.
    if not _session_possible():
        return Unavailable(
            str(
                LLMNotAvailable(
                    f"claude-agent-sdk is installed but the `{_CLI}` CLI is not on PATH, so no "
                    "Claude Code session can be established (typical in a container). Set "
                    f"{_CLI_PATH_ENV} if it lives elsewhere, or configure ANTHROPIC_API_KEY / "
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
