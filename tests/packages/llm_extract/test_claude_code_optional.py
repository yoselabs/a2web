"""`claude-agent-sdk` is an OPTIONAL extra (`a2web[claude-code]`) — the slim
deploy container ships without it (deployable-container-ci §1).

These tests pin the provider-selection delta that the packaging split hinges on:
the `claude-code` rung must GATE on SDK presence (via `find_spec`, cheap — no
heavy import) and degrade to `Unavailable` when absent, so auto-select falls
through to anthropic/openai_compatible rather than crashing on first use.

SDK-absent is simulated by monkeypatching `importlib.util.find_spec` to report
`claude_agent_sdk` missing (the SDK is really installed in the dev env via the
extra, so we can't just uninstall it).
"""

from __future__ import annotations

import importlib.util
import shutil

import pytest

from a2web._manifests.llm_providers import claude_code as manifest
from a2web._plugin import Unavailable
from a2web.llm_resource import select_provider
from a2web.settings import AppSettings

_SDK = "claude_agent_sdk"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep every backend's env-gate under this test's control.
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "CLAUDE_CODE_CLI_PATH"):
        monkeypatch.delenv(var, raising=False)


def _with_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report the `claude` CLI as present on PATH.

    Applied explicitly wherever a test needs the claude-code rung to be
    selectable: CI runners (and containers) have the SDK but no CLI, so without
    this the outcome would depend on the host.
    """
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/claude" if name == "claude" else None)


def _without_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report the `claude` CLI as absent — the containerized-deploy shape."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)


def _hide_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `find_spec('claude_agent_sdk')` report the SDK absent."""
    real = importlib.util.find_spec

    def fake(name: str, package: str | None = None):
        if name == _SDK:
            return None
        return real(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake)


# --------------------------------------------------------------------- #
# Manifest gate on SDK presence
#
# The provider IMPLEMENTATION now lives in the shelf (anyllm's
# `ClaudeCodeSdkAdapter`) — it never raises on construction; usability is probed
# via `available()` (a cheap `find_spec`). a2web's manifest gates on that probe.
# --------------------------------------------------------------------- #


def test_manifest_unavailable_when_sdk_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    _hide_sdk(monkeypatch)
    result = manifest._build(AppSettings())
    assert isinstance(result, Unavailable)
    assert "claude-agent-sdk" in result.reason


def test_manifest_builds_when_sdk_and_cli_present(monkeypatch: pytest.MonkeyPatch) -> None:
    # SDK installed AND the `claude` CLI on PATH → a session is possible. Auth
    # itself is still probed lazily at the first `complete()` (Keychain-backed
    # on macOS), so this does not touch credentials.
    _with_cli(monkeypatch)
    result = manifest._build(AppSettings())
    assert not isinstance(result, Unavailable)
    assert result.name == "claude-code-sdk"


def test_manifest_unavailable_when_sdk_present_but_cli_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The containerized-deploy defect: 0.46.0 bakes the SDK in, but the image
    ships no `claude` CLI and no OAuth session. SDK-importable must NOT count as
    available, or this rung wins `auto` and answers empty forever."""
    _without_cli(monkeypatch)
    result = manifest._build(AppSettings())
    assert isinstance(result, Unavailable)
    assert "claude" in result.reason


def test_manifest_honours_explicit_cli_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """A non-standard CLI location is respected via CLAUDE_CODE_CLI_PATH."""
    _without_cli(monkeypatch)
    cli = tmp_path / "claude"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o755)
    monkeypatch.setenv("CLAUDE_CODE_CLI_PATH", str(cli))
    assert not isinstance(manifest._build(AppSettings()), Unavailable)


def test_manifest_unavailable_when_explicit_cli_path_missing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _with_cli(monkeypatch)  # PATH would say yes; the explicit pin must win
    monkeypatch.setenv("CLAUDE_CODE_CLI_PATH", str(tmp_path / "nope"))
    assert isinstance(manifest._build(AppSettings()), Unavailable)


# --------------------------------------------------------------------- #
# End-to-end auto-select fallthrough (the packaging-split guarantee)
# --------------------------------------------------------------------- #


def test_auto_falls_through_to_anthropic_when_sdk_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """SDK-absent + ANTHROPIC_API_KEY → claude-code drops out, anthropic wins."""
    _hide_sdk(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked[0] == "anthropic"


def test_auto_yields_none_when_sdk_absent_and_no_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """SDK-absent + no other backend keyed → loud None sentinel, not a silent
    live-but-broken claude-code provider."""
    _hide_sdk(monkeypatch)
    assert select_provider(AppSettings(llm_provider="auto")) is None


def test_auto_prefers_claude_code_when_sdk_and_cli_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """SDK + CLI present → claude-code stays first in auto order (unchanged)."""
    _with_cli(monkeypatch)
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked[0] == "claude-code"


# --------------------------------------------------------------------- #
# The containerized-deploy regression (LESSONS_LEARNED #0)
#
# Shape: `claude-agent-sdk` importable (baked into the published image since
# 0.46.0), no Claude Code session, operator's OPENAI_* gateway configured.
# Before the fix, claude-code won `auto` and every `query` returned an empty
# answer while the gateway was never called.
# --------------------------------------------------------------------- #


def test_auto_selects_gateway_when_sdk_present_but_no_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """SDK importable + no session + OPENAI_* set → openai_compatible wins."""
    _without_cli(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://litellm.internal/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked[0] == "openai_compatible"


def test_explicit_gateway_leads_auto_even_when_session_possible(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second, independent guard: an explicitly configured gateway (key + base
    URL) is a deliberate operator act and is never shadowed by a session-based
    backend — even where a Claude Code session IS available."""
    _with_cli(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://litellm.internal/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked[0] == "openai_compatible"


def test_bare_openai_key_does_not_reorder_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ambient OPENAI_API_KEY with no OPENAI_BASE_URL is not an explicit
    gateway configuration, so it must not displace a working session."""
    _with_cli(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked[0] == "claude-code"
