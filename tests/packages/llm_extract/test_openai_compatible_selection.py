"""Selection + model-resolution for the openai-compatible backend.

a2web owns the *policy* here: the OpenAI model recommendation
(`llm_resource._resolve_openai_model`: `OPENAI_MODEL` → host recommendation →
`None` = unresolvable, so the backend drops from the order rather than sending an
OpenAI endpoint no model) and the fallback-last ordering (never shadows a working
Claude/Anthropic path). anyllm owns construction + availability; `select_provider`
returns a live `LLMProvider` (its `.name` is the winning `ProviderName`) or `None`.
"""

from __future__ import annotations

import pytest
from anyllm import ClaudeCodeSdkAdapter, ProviderName

from a2web import llm_resource
from a2web.llm_resource import select_provider
from a2web.settings import AppSettings

_KEY_ENV = "OPENAI_API_KEY"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (_KEY_ENV, "OPENAI_BASE_URL", "OPENAI_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    # Sessions are off unless a test opts in — keep selection host-independent.
    monkeypatch.setattr(ClaudeCodeSdkAdapter, "available", lambda _self: False)


# --------------------------------------------------------------------- #
# Model resolution (a2web policy): OPENAI_MODEL → host recommendation → None
# --------------------------------------------------------------------- #


def test_resolve_explicit_model_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "mistral-small-latest")
    assert llm_resource._resolve_openai_model("https://anything/v1") == "mistral-small-latest"


def test_resolve_unset_base_url_recommends_openai() -> None:
    # Empty base_url → OpenAI proper → its recommended default.
    assert llm_resource._resolve_openai_model("") == "gpt-4.1-mini"


def test_resolve_gemini_host_recommends_flash() -> None:
    assert llm_resource._resolve_openai_model("https://generativelanguage.googleapis.com/v1beta/openai") == "gemini-2.5-flash"


def test_resolve_unknown_host_no_model_is_none() -> None:
    # OpenRouter / local: no single sensible default → require OPENAI_MODEL.
    assert llm_resource._resolve_openai_model("https://openrouter.ai/api/v1") is None


# --------------------------------------------------------------------- #
# Order policy: openai-compatible is last (never shadows Claude/Anthropic)
# --------------------------------------------------------------------- #


def test_openai_compatible_is_last_in_auto_order() -> None:
    order = llm_resource._PROVIDER_ORDER
    assert order[-1] == ProviderName.OPENAI_COMPATIBLE
    assert order.index(ProviderName.CLAUDE_CODE_SDK) < order.index(ProviderName.OPENAI_COMPATIBLE)
    assert order.index(ProviderName.ANTHROPIC_API) < order.index(ProviderName.OPENAI_COMPATIBLE)


# --------------------------------------------------------------------- #
# Selection: fallback-last, derived-when-alone, pin, unconfigured
# --------------------------------------------------------------------- #


def test_auto_prefers_anthropic_over_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both anthropic and a gateway keyed, no explicit gateway (no BASE_URL) →
    anthropic wins; openai-compatible is present but last, never shadows."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv(_KEY_ENV, "k")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")  # makes openai resolvable
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked.name == ProviderName.ANTHROPIC_API


def test_auto_derives_openai_when_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """No claude/anthropic (e.g. slim container) + a keyed, model-resolvable
    gateway → openai-compatible is derived, no explicit pin needed."""
    monkeypatch.setenv(_KEY_ENV, "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")  # recognized → recommendation
    picked = select_provider(AppSettings(llm_provider="auto"))
    assert picked is not None
    assert picked.name == ProviderName.OPENAI_COMPATIBLE


def test_explicit_pin_selects_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")  # present but not pinned
    monkeypatch.setenv(_KEY_ENV, "k")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    picked = select_provider(AppSettings(llm_provider=ProviderName.OPENAI_COMPATIBLE))
    assert picked is not None
    assert picked.name == ProviderName.OPENAI_COMPATIBLE


def test_default_model_survives_the_timeout_wrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: `select_provider()` always wraps its result in `TimeoutProvider`
    (`llm_timeout_s` defaults to 180 in `AppSettings`), and that wrapper used to
    forward only `.name`/`.available()` — not `.default_model`. A caller reading
    `getattr(provider, "default_model", "")` off the REAL returned provider (not a
    bare adapter) always missed and silently fell back to the Anthropic default,
    even with `OPENAI_MODEL` correctly configured."""
    monkeypatch.setenv(_KEY_ENV, "k")
    monkeypatch.setenv("OPENAI_MODEL", "openrouter/openai/gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    picked = select_provider(AppSettings(llm_provider=ProviderName.OPENAI_COMPATIBLE))
    assert picked is not None
    assert getattr(picked, "default_model", "") == "openrouter/openai/gpt-4.1-mini"


def test_pin_openai_without_model_yields_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keyed but no resolvable model (unknown host, no OPENAI_MODEL) → the
    backend drops from the order → pin resolves to nothing, never a modelless
    OpenAI call."""
    monkeypatch.setenv(_KEY_ENV, "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")  # unrecognized, no OPENAI_MODEL
    assert select_provider(AppSettings(llm_provider=ProviderName.OPENAI_COMPATIBLE)) is None


def test_pin_openai_without_key_yields_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model resolvable but no API key → adapter unavailable → None (not a
    silent degrade)."""
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    assert select_provider(AppSettings(llm_provider=ProviderName.OPENAI_COMPATIBLE)) is None
