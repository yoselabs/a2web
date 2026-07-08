"""Anthropic provider manifest — wraps anyllm's `AnthropicApiAdapter` construction
with capability check + `AppSettings` reads."""

from __future__ import annotations

from anyllm import AnthropicApiAdapter

from a2web._plugin import PluginManifest, Unavailable
from a2web.packages.llm_extract import LLMNotAvailable, Provider
from a2web.settings import AppSettings


def _build(settings: AppSettings) -> Provider | Unavailable:
    # anyllm adapters never raise on construction — they surface usability via
    # `available()`. Gate on it and preserve a2web's actionable `LLMNotAvailable`
    # message (mapped to `Unavailable`) for the missing-key case.
    adapter = AnthropicApiAdapter(api_key_env=settings.llm_api_key_env)
    if not adapter.available():
        return Unavailable(
            str(
                LLMNotAvailable(
                    f"No Anthropic API key found. Set the {settings.llm_api_key_env} environment "
                    "variable to a valid key from https://console.anthropic.com/."
                )
            )
        )
    return adapter


MANIFEST = PluginManifest(
    name="anthropic",
    protocol=Provider,
    factory=_build,
    requires=("llm_api_key_env",),
)
