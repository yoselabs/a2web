"""Claude Code provider manifest — piggybacks on the OS session via anyllm's
`ClaudeCodeSdkAdapter`. Returns Unavailable when the backend is not usable."""

from __future__ import annotations

from anyllm import ClaudeCodeSdkAdapter

from a2web._plugin import PluginManifest, Unavailable
from a2web.packages.llm_extract import LLMNotAvailable, Provider
from a2web.settings import AppSettings


def _build(_settings: AppSettings) -> Provider | Unavailable:
    # anyllm's adapter never raises on construction — it reports usability via
    # `available()`. Since anyllm v0.4.0 that means genuinely usable: a `claude`
    # CLI it can spawn AND a session credential to spawn it with. Before that it
    # only checked whether the Python package was importable, which made this
    # rung claim availability inside a container that bakes in the extra — it
    # then won a2web's `auto` order and returned empty answers forever while the
    # operator's configured OPENAI_* gateway was never consulted.
    #
    # a2web deliberately does NOT re-probe here. The CLI is bundled inside the
    # SDK package, so naive checks (`shutil.which("claude")`) disagree with what
    # the adapter will actually do — the probe belongs next to the code that
    # spawns the process. Gate on `available()` and keep a2web's actionable
    # `LLMNotAvailable` message for the operator.
    adapter = ClaudeCodeSdkAdapter()
    if not adapter.available():
        return Unavailable(
            str(
                LLMNotAvailable(
                    "Claude Code backend not usable — either `claude-agent-sdk` is not installed "
                    "(`pip install a2web[claude-code]`) or no logged-in Claude Code session was "
                    "found (typical in a container: run `claude` once to log in, or set "
                    "CLAUDE_CODE_OAUTH_TOKEN). Alternatively set ANTHROPIC_API_KEY / OPENAI_API_KEY "
                    "to use a different backend."
                )
            )
        )
    return adapter


MANIFEST = PluginManifest(
    name="claude-code",
    protocol=Provider,
    factory=_build,
)
