"""OpenAI-compatible provider manifest — standard-env config + recommendations.

Gates on the standard `OPENAI_API_KEY` (via the configured key-env indirection);
absent it, reports `Unavailable` so the backend drops out of the registry. When
keyed, it derives as the LAST-resort fallback in the auto order
(`llm_resource._PROVIDER_ORDER`) — it can never shadow a working Claude/Anthropic
path, so no explicit pin is needed.

Model resolution (no universal standard var, so a2web supplies recommendations):
`OPENAI_MODEL` env → host-keyed recommended default (info log) → loud
`Unavailable` listing the recommendations. Never falls back to the Anthropic
`llm_model` default (that would send a Claude id to an OpenAI endpoint).

Recommendation IDs are mid-2026 starting points the bench ratifies; they live in
one table so they are cheap to refresh. OpenRouter / local / any unrecognized
host has no default on purpose — the operator names `OPENAI_MODEL` explicitly
(OpenRouter multiplexes many models; a single default would be wrong).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from anyllm import OpenAICompatibleAdapter

from a2web._plugin import PluginManifest, Unavailable
from a2web.log import log_info
from a2web.packages.llm_extract import LLMNotAvailable, Provider
from a2web.settings import AppSettings


@dataclass(frozen=True, slots=True)
class BackendRecommendation:
    """A curated cheap/high-quality default model for a recognized host."""

    host_match: str  # substring matched against the OPENAI_BASE_URL netloc
    label: str
    model: str


# Quality-first-under-Haiku's-cost picks (mid-2026). Reconfirmed by the bench.
# OpenRouter/local are deliberately absent — they require an explicit OPENAI_MODEL.
RECOMMENDED_BACKENDS: tuple[BackendRecommendation, ...] = (
    BackendRecommendation("api.deepseek.com", "DeepSeek", "deepseek-v4-flash"),
    BackendRecommendation("generativelanguage.googleapis.com", "Gemini", "gemini-2.5-flash"),
    BackendRecommendation("api.openai.com", "OpenAI", "gpt-4.1-mini"),
)

# Empty OPENAI_BASE_URL means the SDK targets OpenAI proper.
_DEFAULT_HOST = "api.openai.com"


def _recommend(base_url: str) -> BackendRecommendation | None:
    host = urlparse(base_url).netloc or _DEFAULT_HOST if base_url else _DEFAULT_HOST
    for rec in RECOMMENDED_BACKENDS:
        if rec.host_match in host:
            return rec
    return None


def _resolve_model(base_url: str) -> str | Unavailable:
    """OPENAI_MODEL → host recommendation (logged) → loud Unavailable."""
    explicit = os.environ.get("OPENAI_MODEL", "").strip()
    if explicit:
        return explicit
    rec = _recommend(base_url)
    if rec is not None:
        log_info(
            "openai_compatible.model_recommended",
            model=rec.model,
            backend=rec.label,
            base_url=base_url or _DEFAULT_HOST,
            override="set OPENAI_MODEL to override",
        )
        return rec.model
    names = ", ".join(f"{r.label}={r.model}" for r in RECOMMENDED_BACKENDS)
    return Unavailable(
        f"openai_compatible: set OPENAI_MODEL — no recommended default for base_url "
        f"'{base_url or _DEFAULT_HOST}' (recognized hosts: {names})"
    )


def _build(settings: AppSettings) -> Provider | Unavailable:
    if not os.environ.get(settings.llm_openai_api_key_env, "").strip():
        return Unavailable(f"openai_compatible: {settings.llm_openai_api_key_env} not set")
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    model = _resolve_model(base_url)
    if isinstance(model, Unavailable):
        return model
    # anyllm's adapter never raises on construction; `available()` re-checks the
    # key env. The explicit key-gate above already returns a2web's specific
    # message, so a failing `available()` here is only a belt-and-suspenders
    # guard. `default_model` (the OPENAI_MODEL / host-recommendation resolution)
    # rides on the adapter so the resolved model travels with the provider.
    adapter = OpenAICompatibleAdapter(
        base_url=base_url,
        api_key_env=settings.llm_openai_api_key_env,
        default_model=model,
    )
    if not adapter.available():
        return Unavailable(
            str(
                LLMNotAvailable(
                    f"No OpenAI-compatible API key found. Set the {settings.llm_openai_api_key_env} environment variable."
                )
            )
        )
    log_info(
        "openai_compatible.active",
        base_url=base_url or _DEFAULT_HOST,
        model=model,
    )
    return adapter


MANIFEST = PluginManifest(
    name="openai_compatible",
    protocol=Provider,
    factory=_build,
    requires=("llm_openai_api_key_env",),
)
