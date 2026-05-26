"""Anthropic provider manifest — wraps `AnthropicProvider` construction with
capability check + `AppSettings` reads."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.packages.llm_extract import LLMNotAvailable, Provider
from a2web.packages.llm_extract.providers.anthropic import AnthropicProvider
from a2web.settings import AppSettings


def _build(settings: AppSettings) -> Provider | Unavailable:
    try:
        return AnthropicProvider(api_key_env=settings.llm_api_key_env)
    except LLMNotAvailable as exc:
        return Unavailable(str(exc))


MANIFEST = PluginManifest(
    name="anthropic",
    protocol=Provider,
    factory=_build,
    requires=("llm_api_key_env",),
)
