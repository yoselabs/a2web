"""Provider-selection policy: the `claude-code` (SDK-session) rung and auto-order.

a2web's provider *construction + availability* now live in the shelf (anyllm's
`resolve_provider` + adapters); a2web owns the *policy* — the order, the
gateway-first reorder, and the model recommendation (`llm_resource`). These
tests pin that policy end-to-end through `select_provider`, which returns a live
`anyllm.LLMProvider` (its `.name` is the winning `ProviderName`) or `None`.

`claude-code` maps to anyllm's `ClaudeCodeSdkAdapter` (a2web piggybacks the OS
session via `claude-agent-sdk`). Whether that backend is *usable* — CLI present
AND a logged-in session — is anyllm's `available()` verdict; a2web consumes it.
Since a CI runner has neither session nor Keychain, we pin `available()` per
test so these stay about SELECTION POLICY, not the host they run on.
"""

from __future__ import annotations

import pytest
from anyllm import ClaudeCodeSdkAdapter, ProviderName

from a2web.llm_resource import select_provider
from a2web.settings import AppSettings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep every backend's env-gate under this test's control.
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        monkeypatch.delenv(var, raising=False)


def _session(monkeypatch: pytest.MonkeyPatch, *, usable: bool) -> None:
    """Pin the claude-code backend's usability (CLI + logged-in session)."""
    monkeypatch.setattr(ClaudeCodeSdkAdapter, "available", lambda _self: usable)


# --------------------------------------------------------------------- #
# Auto-select fallthrough (the packaging-split guarantee)
# --------------------------------------------------------------------- #


def test_auto_falls_through_to_anthropic_when_no_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """No Claude session + ANTHROPIC_API_KEY → claude-code drops out, anthropic wins."""
    _session(monkeypatch, usable=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked.name == ProviderName.ANTHROPIC_API


def test_auto_yields_none_when_no_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """No session + no other backend keyed → loud None sentinel, not a silent
    live-but-broken provider."""
    _session(monkeypatch, usable=False)
    assert select_provider(AppSettings(llm_provider="auto")) is None


def test_auto_prefers_claude_code_when_session_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Session usable → claude-code stays first in auto order."""
    _session(monkeypatch, usable=True)
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked.name == ProviderName.CLAUDE_CODE_SDK


# --------------------------------------------------------------------- #
# The containerized-deploy regression (LESSONS_LEARNED #0)
#
# Shape: `claude-agent-sdk` importable (baked into the published image), no
# Claude Code session, operator's OPENAI_* gateway configured. Before the fix,
# claude-code won `auto` and every `query` returned an empty answer while the
# gateway was never called.
# --------------------------------------------------------------------- #


def test_auto_selects_gateway_when_no_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """No session + OPENAI_* set → openai_compatible wins."""
    _session(monkeypatch, usable=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://litellm.internal/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked.name == ProviderName.OPENAI_COMPATIBLE


def test_explicit_gateway_leads_auto_even_when_session_possible(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second, independent guard: an explicitly configured gateway (key + base
    URL) is a deliberate operator act and is never shadowed by a session-based
    backend — even where a Claude Code session IS usable."""
    _session(monkeypatch, usable=True)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://litellm.internal/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked.name == ProviderName.OPENAI_COMPATIBLE


def test_bare_openai_key_does_not_reorder_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ambient OPENAI_API_KEY with no OPENAI_BASE_URL is not an explicit
    gateway configuration, so it must not displace a working session."""
    _session(monkeypatch, usable=True)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked.name == ProviderName.CLAUDE_CODE_SDK
