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

import pytest

from a2web._manifests.llm_providers import claude_code as manifest
from a2web._plugin import Unavailable
from a2web.llm_resource import select_provider
from a2web.settings import AppSettings

_SDK = "claude_agent_sdk"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep every backend's env-gate under this test's control.
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        monkeypatch.delenv(var, raising=False)


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


def test_manifest_builds_when_sdk_present() -> None:
    # Dev env has the extra installed → adapter is available (session detection
    # is deferred to the first `complete()` call, so this does not touch auth).
    result = manifest._build(AppSettings())
    assert not isinstance(result, Unavailable)
    assert result.name == "claude-code-sdk"


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


def test_auto_prefers_claude_code_when_sdk_present() -> None:
    """SDK-present → claude-code stays first in auto order (unchanged behavior)."""
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked[0] == "claude-code"
