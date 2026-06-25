"""LlmExtractorResource — lazy-init Extractor wrapper.

a2kit v0.36+ Lazy[T] resource: framework enters via `__aenter__` only when
a tool actually awaits its `Lazy[LlmExtractorResource]` param. The
underlying Extractor builds on first `_ensure()` to keep construction
cheap and decouple provider selection from import time.

As of a2web v0.7, `anthropic` + `claude-agent-sdk` are baseline deps —
the prior `[llm]` extra was removed. `--ask` works out of the box.

Provider selection follows `settings.llm_provider`:
- ``auto``         — try ClaudeCode (OS session via `claude-agent-sdk`)
                     first; fall back to Anthropic API.
- ``anthropic``    — direct Anthropic Messages API; requires API key.
- ``claude-code``  — Claude Code OS session only.

The `_ensure()` contract returns `None` on permanent unavailability
(missing API key AND no Claude Code OAuth session). Transient SDK
errors propagate normally. Callers branch on the None return and
populate an OperatorHint without retrying construction.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .settings import AppSettings

if TYPE_CHECKING:
    from a2kit.packages.di import Lazy

    from .packages.http_cache import SqliteResource
    from .packages.llm_extract import ExtractionResult, Extractor, LlmNextLink, Provider


# The provider preference order, declared once. Claude Code's OS session
# (OAuth subscription — no `ANTHROPIC_API_KEY`) is preferred; the Anthropic
# API provider is the credential-bearing fallback. This is the single source
# of truth for both the production `ask` path and the bench harness.
_PROVIDER_SURFACE = "a2web._manifests.llm_providers"
_PROVIDER_ORDER = ("claude-code", "anthropic")


def select_provider(settings: AppSettings, *, override: str | None = None) -> tuple[str, Provider] | None:
    """Pick an LLM provider from the manifest registry, or return None.

    The manifest registry (`_manifests/llm_providers/`) decides *what can be
    built* — unconfigured backends drop out as `Unavailable`. This function
    layers the *selection policy* on top: a pinned provider (`override`, or a
    concrete `settings.llm_provider`) is tried alone; `auto` walks
    `_PROVIDER_ORDER` (claude-code first, anthropic fallback) and takes the
    first present entry.

    Returns `(provider_id, provider)` where `provider_id` is the winning
    manifest name (the same string `settings.llm_provider` accepts), or
    `None` when nothing in `order` is registrable. Callers supply their own
    error-shaping around `None` (silent degrade vs. raise).
    """
    from ._plugin import load_surface
    from .packages.llm_extract import Provider

    registry = load_surface(_PROVIDER_SURFACE, Provider, settings)
    pin = override or settings.llm_provider
    order = _PROVIDER_ORDER if pin == "auto" else (pin,)
    for name in order:
        if name in registry:
            return name, registry[name]
    return None


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
        from .packages.llm_extract import ExtractionCache, Extractor, ModelSpec
        from .packages.llm_extract.prompts import EXTRACT_CACHEABLE_V1

        s = self._settings
        provider = await self._provider()

        # Hook the extraction cache into the same sqlite file as the HTTP
        # cache. Ensures the underlying connection is open first.
        try:
            conn = await self._sqlite._ensure()
        except Exception as exc:  # sqlite open failure shouldn't block extraction
            cache: ExtractionCache | None = None
            del exc
        else:
            cache = ExtractionCache(conn, ttl_s=s.extraction_cache_ttl_s)

        return Extractor(
            provider=provider,
            model=ModelSpec(s.llm_model),
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
