"""Manifest + selection + model-resolution tests for the openai_compatible backend.

Covers the `provider-selection` delta: standard-env config-gating (no
`OPENAI_API_KEY` → Unavailable), model resolution (`OPENAI_MODEL` → host
recommendation → fail loud), derived fallback-last selection (never shadows
Claude/Anthropic; used when they are absent), and explicit pin.
"""

from __future__ import annotations

import types

import pytest

from a2web import llm_resource
from a2web._manifests.llm_providers import openai_compatible as manifest
from a2web._plugin import Unavailable
from a2web.llm_resource import select_provider
from a2web.settings import AppSettings

_KEY_ENV = "OPENAI_API_KEY"


def _install_fake_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        def __init__(self, **kw: object) -> None:
            self.chat = types.SimpleNamespace(completions=object())

    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _Client)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (_KEY_ENV, "OPENAI_BASE_URL", "OPENAI_MODEL"):
        monkeypatch.delenv(var, raising=False)


# --------------------------------------------------------------------- #
# Manifest: standard-env gating
# --------------------------------------------------------------------- #


def test_manifest_unavailable_when_no_key() -> None:
    result = manifest._build(AppSettings())  # OPENAI_API_KEY unset (clean_env)
    assert isinstance(result, Unavailable)


def test_manifest_builds_with_key_and_recognized_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_KEY_ENV, "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    _install_fake_openai(monkeypatch)
    result = manifest._build(AppSettings())
    assert not isinstance(result, Unavailable)
    assert result.name == "openai_compatible"
    assert result.default_model == "deepseek-v4-flash"  # host recommendation


def test_manifest_builds_with_explicit_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_KEY_ENV, "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENAI_MODEL", "qwen/qwen-2.5-72b-instruct")
    _install_fake_openai(monkeypatch)
    result = manifest._build(AppSettings())
    assert not isinstance(result, Unavailable)
    assert result.default_model == "qwen/qwen-2.5-72b-instruct"


# --------------------------------------------------------------------- #
# Model resolution
# --------------------------------------------------------------------- #


def test_resolve_explicit_model_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "mistral-small-latest")
    assert manifest._resolve_model("https://anything/v1") == "mistral-small-latest"


def test_resolve_unset_base_url_recommends_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    # Empty base_url → OpenAI proper → its recommended default.
    assert manifest._resolve_model("") == "gpt-4.1-mini"


def test_resolve_gemini_host_recommends_flash() -> None:
    assert manifest._resolve_model("https://generativelanguage.googleapis.com/v1beta/openai") == "gemini-2.5-flash"


def test_resolve_unknown_host_no_model_fails_loud() -> None:
    # OpenRouter / local: no single sensible default → require OPENAI_MODEL.
    result = manifest._resolve_model("https://openrouter.ai/api/v1")
    assert isinstance(result, Unavailable)
    assert "OPENAI_MODEL" in result.reason


def test_manifest_unknown_host_no_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_KEY_ENV, "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    _install_fake_openai(monkeypatch)
    result = manifest._build(AppSettings())
    assert isinstance(result, Unavailable)


# --------------------------------------------------------------------- #
# Selection: derived fallback-last, pin, invariants
# --------------------------------------------------------------------- #


def _fake_registry(monkeypatch: pytest.MonkeyPatch, registry: dict[str, object]) -> None:
    monkeypatch.setattr("a2web._plugin.load_surface", lambda *_a: registry)


def test_openai_compatible_is_last_in_auto_order() -> None:
    assert llm_resource._PROVIDER_ORDER[-1] == "openai_compatible"
    # Preferred backends come first — never shadowed.
    assert llm_resource._PROVIDER_ORDER.index("claude-code") < llm_resource._PROVIDER_ORDER.index("openai_compatible")
    assert llm_resource._PROVIDER_ORDER.index("anthropic") < llm_resource._PROVIDER_ORDER.index("openai_compatible")


def test_auto_prefers_claude_over_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    cc = types.SimpleNamespace(name="claude-code")
    _fake_registry(monkeypatch, {"claude-code": cc, "openai_compatible": object()})
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked[0] == "claude-code"  # openai_compatible present but last → never shadows


def test_auto_derives_openai_when_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    oc = types.SimpleNamespace(name="openai_compatible")
    _fake_registry(monkeypatch, {"openai_compatible": oc})  # no claude/anthropic (e.g. slim container)
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked[0] == "openai_compatible"  # derived, no explicit pin


def test_explicit_pin_selects_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    oc = types.SimpleNamespace(name="openai_compatible")
    _fake_registry(monkeypatch, {"anthropic": object(), "openai_compatible": oc})
    picked = select_provider(AppSettings(llm_provider="openai_compatible"))
    assert picked is not None
    assert picked[0] == "openai_compatible"


def test_pin_without_config_yields_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # Unconfigured → manifest Unavailable → absent from registry → pin resolves
    # to nothing rather than silently degrading.
    _fake_registry(monkeypatch, {"anthropic": object()})
    assert select_provider(AppSettings(llm_provider="openai_compatible")) is None
