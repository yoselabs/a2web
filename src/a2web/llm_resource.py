"""LlmExtractorResource — lazy-init Extractor wrapper.

a2kit v0.36+ Lazy[T] resource: framework enters via `__aenter__` only when
a tool actually awaits its `Lazy[LlmExtractorResource]` param. The
underlying Extractor builds on first `_ensure()` to keep construction
cheap and decouple provider selection from import time.

As of a2web v0.7, `anthropic` + `claude-agent-sdk` are baseline deps —
the prior `[llm]` extra was removed. `--ask` works out of the box.

Provider selection follows `settings.llm_provider` (`A2WEB_LLM_PROVIDER`):
- ``auto``               — ClaudeCode (OS session via `claude-agent-sdk`) first,
                           then Anthropic API, then the OpenAI-compatible
                           gateway. When `OPENAI_API_KEY` *and* `OPENAI_BASE_URL`
                           are both set, that gateway leads instead — an explicit
                           operator configuration is never shadowed by a
                           session-based backend.
- ``anthropic``          — direct Anthropic Messages API; requires API key.
- ``claude-code``        — Claude Code OS session only; requires both the
                           `claude-agent-sdk` package and the `claude` CLI.
- ``openai_compatible``  — any OpenAI-compatible gateway (`OPENAI_BASE_URL`).

The `_ensure()` contract returns `None` on permanent unavailability
(missing API key AND no Claude Code OAuth session). Transient SDK
errors propagate normally. Callers branch on the None return and
populate an OperatorHint without retrying construction.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, assert_never

from anyllm import ProviderName, resolve_provider

from .log import log_info
from .settings import AppSettings

if TYPE_CHECKING:
    from anyllm import LLMProvider

    from .cache import SqliteResource
    from .lazy import Lazy
    from .packages.llm_extract import ExtractionResult, Extractor, LlmNextLink, Provider


# The provider preference order, declared once (a2web policy — anyllm owns
# construction + availability + the ordered walk; a2web owns which backends, in
# what priority). Claude Code's OS session (OAuth subscription — no
# `ANTHROPIC_API_KEY`) is preferred; the Anthropic API is the credential-bearing
# fallback; `openai-compatible` is the LAST-resort gateway. Placing it last means
# a configured OpenAI key can never SHADOW a working Claude/Anthropic path.
#
# a2web's `claude-code` is the SDK-piggyback session, so it maps to anyllm's
# CLAUDE_CODE_SDK. anyllm's `available()` (v0.4.0+) genuinely probes CLI + session
# — the old container-empties bug (LESSONS_LEARNED #0) is fixed at the source, so
# a2web no longer re-probes here; the explicit-gateway reorder below is the second
# guard. Single source of truth for the production `ask` path and the bench.
_PROVIDER_ORDER: tuple[ProviderName, ...] = (
    ProviderName.CLAUDE_CODE_SDK,
    ProviderName.ANTHROPIC_API,
    ProviderName.OPENAI_COMPATIBLE,
)
# When the operator has explicitly pointed a2web at an OpenAI-compatible
# gateway, that is a deliberate configuration act — not an ambient fallback —
# so it leads the `auto` order instead of trailing it. `OPENAI_BASE_URL` is the
# intent signal (a bare `OPENAI_API_KEY` may just be ambient in a shell), which
# is why both must be present to reorder.
_GATEWAY_FIRST_ORDER: tuple[ProviderName, ...] = (
    ProviderName.OPENAI_COMPATIBLE,
    ProviderName.CLAUDE_CODE_SDK,
    ProviderName.ANTHROPIC_API,
)


@dataclass(frozen=True, slots=True)
class BackendRecommendation:
    """A curated cheap/high-quality default model for a recognized gateway host."""

    host_match: str  # substring matched against the OPENAI_BASE_URL netloc
    label: str
    model: str


# Quality-first-under-Haiku's-cost picks (mid-2026); the bench reconfirms them.
# OpenRouter/local are deliberately absent — they require an explicit OPENAI_MODEL
# (OpenRouter multiplexes many models; a single default would be wrong). This is
# a2web PRODUCT policy (which cheap model to default to per gateway), not
# substrate — anyllm builds from a `default_model`, it does not recommend one.
RECOMMENDED_BACKENDS: tuple[BackendRecommendation, ...] = (
    BackendRecommendation("api.deepseek.com", "DeepSeek", "deepseek-v4-flash"),
    BackendRecommendation("generativelanguage.googleapis.com", "Gemini", "gemini-2.5-flash"),
    BackendRecommendation("api.openai.com", "OpenAI", "gpt-4.1-mini"),
)
_DEFAULT_OPENAI_HOST = "api.openai.com"  # empty OPENAI_BASE_URL targets OpenAI proper


def _recommend_openai_model(base_url: str) -> BackendRecommendation | None:
    from urllib.parse import urlparse

    host = urlparse(base_url).netloc or _DEFAULT_OPENAI_HOST if base_url else _DEFAULT_OPENAI_HOST
    return next((rec for rec in RECOMMENDED_BACKENDS if rec.host_match in host), None)


def _resolve_openai_model(base_url: str) -> str | None:
    """OPENAI_MODEL → host recommendation (logged) → None (unresolvable)."""
    explicit = os.environ.get("OPENAI_MODEL", "").strip()
    if explicit:
        return explicit
    rec = _recommend_openai_model(base_url)
    if rec is None:
        return None
    log_info(
        "openai_compatible.model_recommended",
        model=rec.model,
        backend=rec.label,
        base_url=base_url or _DEFAULT_OPENAI_HOST,
        override="set OPENAI_MODEL to override",
    )
    return rec.model


def _explicit_gateway_configured(settings: AppSettings) -> bool:
    """True when OPENAI_API_KEY *and* OPENAI_BASE_URL are both explicitly set."""
    return bool(os.environ.get(settings.llm_openai_api_key_env, "").strip() and os.environ.get("OPENAI_BASE_URL", "").strip())


def auto_order(settings: AppSettings) -> tuple[ProviderName, ...]:
    """The `auto` preference order for these settings/env.

    Single source of truth for auto-mode precedence (the architecture test pins
    that no other module hardcodes an order).
    """
    return _GATEWAY_FIRST_ORDER if _explicit_gateway_configured(settings) else _PROVIDER_ORDER


def _config_for(name: ProviderName, settings: AppSettings) -> dict | None:
    """The `anyllm.build_adapter` config sub-dict for one backend, or None to
    exclude it from the order.

    The exhaustive `match` (no wildcard) is the §7.4 static guard: a new
    `anyllm.ProviderName` fails `assert_never` at build time rather than silently
    resolving to an empty config.
    """
    match name:
        case ProviderName.CLAUDE_CODE_CLI | ProviderName.CLAUDE_CODE_SDK:
            return {}  # session backends take no a2web config
        case ProviderName.ANTHROPIC_API:
            return {"anthropic_api": {"api_key_env": settings.llm_api_key_env}}
        case ProviderName.OPENAI_COMPATIBLE:
            base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
            model = _resolve_openai_model(base_url)
            if model is None:
                # No OPENAI_MODEL and no recommendation for this host → drop the
                # backend rather than send an OpenAI endpoint no model (was the
                # manifest's loud `Unavailable`). A Claude id must never leak here.
                return None
            return {"openai_compatible": {"base_url": base_url, "api_key_env": settings.llm_openai_api_key_env, "default_model": model}}
        case _:
            assert_never(name)


def select_provider(settings: AppSettings, *, override: ProviderName | str | None = None) -> LLMProvider | None:
    """Pick an LLM provider (or a runtime-fallback over several), or return None.

    a2web owns the *policy* — the order (`auto_order`, gateway-first when a
    gateway is explicitly configured) and each backend's config (`_config_for`,
    including the a2web OpenAI model recommendation). anyllm owns the *mechanism*:
    `resolve_provider` builds each candidate via `build_adapter`, drops the
    unbuildable/unavailable, and folds the survivors into one provider — a bare
    provider for a single survivor, a runtime-fallback provider for several (it
    advances to the next backend on a retryable failure; a `CostViolation`
    propagates, never spending to recover).

    A pinned `override`/`settings.llm_provider` is tried alone; `auto` walks the
    order. Returns `None` when nothing is usable (callers shape their own
    degrade-vs-raise around it).
    """
    pin = override or settings.llm_provider
    order: tuple[ProviderName, ...] = auto_order(settings) if pin == "auto" else (ProviderName(pin),)
    merged: dict = {}
    effective: list[ProviderName] = []
    for name in order:
        cfg = _config_for(name, settings)
        if cfg is None:
            continue  # a2web policy excluded it (e.g. openai with no resolvable model)
        merged.update(cfg)
        effective.append(name)
    if not effective:
        return None
    return resolve_provider(effective, merged, fallback=True)


class LlmExtractorResource:
    """Wraps `Extractor` with lazy construction + cache wiring around an
    injected `Lazy[Provider]`.

    The provider is supplied (not selected internally): production registers
    `select_provider` as the `Provider` DI factory; bench/tests pass a
    `Lazy[Provider]` directly. "No provider configured" rides the shared
    `ResourceUnavailable` seam — awaiting an unavailable provider raises, and
    the orchestrator degrades to raw + an operator hint.
    """

    def __init__(self, settings: AppSettings, sqlite: SqliteResource, provider: Lazy[Provider]) -> None:
        self._settings = settings
        self._sqlite = sqlite
        self._provider = provider
        self._extractor: Extractor | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> Extractor:
        """Construct the Extractor on first call; cached thereafter.

        Awaits the injected provider — when no provider is configured the
        await raises `ResourceUnavailable`, which propagates to the caller.
        """
        if self._extractor is not None:
            return self._extractor
        async with self._lock:
            if self._extractor is not None:
                return self._extractor
            self._extractor = await self._build()
            return self._extractor

    async def _build(self) -> Extractor:
        """Build an `Extractor` around the injected provider + extraction cache.

        Resolves the provider from the injected `Lazy[Provider]`; an
        unavailable provider raises `ResourceUnavailable` here.
        """
        from .packages.llm_extract import Extractor, LlmCache, ModelSpec
        from .packages.llm_extract.prompts import EXTRACT_CACHEABLE_V1

        s = self._settings
        provider = await self._provider()

        # Hook the extraction cache into the same sqlite file as the HTTP
        # cache. Ensures the underlying connection is open first.
        try:
            conn = await self._sqlite.ensure()
        except Exception as exc:  # sqlite open failure shouldn't block extraction
            cache: LlmCache | None = None
            del exc
        else:
            cache = LlmCache(conn, ttl_s=s.extraction_cache_ttl_s)

        # A provider may carry its own resolved model (openai_compatible sets
        # `default_model` from OPENAI_MODEL / a host recommendation); it wins over
        # the Anthropic-shaped `llm_model` default so a Claude id is never sent
        # to an OpenAI endpoint.
        model_id = getattr(provider, "default_model", "") or s.llm_model

        return Extractor(
            provider=provider,
            model=ModelSpec(model_id),
            template=EXTRACT_CACHEABLE_V1,
            max_content_chars=s.extraction_max_chars,
            cache=cache,
        )

    async def extract(
        self,
        *,
        content: str,
        ask: str,
        request_next_links: bool = False,
        handler_candidates: list[LlmNextLink] | None = None,
        max_content_chars: int | None = None,
        request_routing: bool = False,
        link_digest: str | None = None,
    ) -> ExtractionResult:
        """Run extraction. Raises `ResourceUnavailable` when no LLM provider
        is configured — the orchestrator catches it and degrades to raw.

        `request_next_links` and `handler_candidates` opt into v0.7
        link-discovery Tier 2 output. `handler_candidates` is `list[LlmNextLink]`
        but typed as `list[Any]` here to avoid leaking the package boundary
        type onto the resource signature; the extractor enforces shape.

        `max_content_chars` overrides the extractor's per-call default for
        a single fetch (v0.10 harsh-test-session-fixes). `None` = use the
        extractor's configured default.
        """
        extractor = await self._ensure()
        return await extractor.extract(
            content=content,
            ask=ask,
            request_next_links=request_next_links,
            handler_candidates=handler_candidates,
            max_content_chars=max_content_chars,
            request_routing=request_routing,
            link_digest=link_digest,
        )

    async def close(self) -> None:
        """No-op today; symmetric with sqlite/browser for lifecycle hooks."""
        return None

    # Framework-facing async-CM protocol (a2kit v0.36+). Entry is cheap —
    # provider construction is deferred to the first `extract()` so the
    # "no provider" case surfaces uniformly at the extract seam (tests inject
    # via `a2kit.testing.lazy`, which bypasses `__aenter__`).
    async def __aenter__(self) -> LlmExtractorResource:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()


__all__ = ["LlmExtractorResource"]
