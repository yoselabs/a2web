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
    from .packages.http_cache import SqliteResource
    from .packages.llm_extract import ExtractionResult, Extractor, LlmNextLink


class LlmExtractorResource:
    """Wraps `Extractor` with lazy construction + provider fallback + cache wiring."""

    def __init__(self, settings: AppSettings, sqlite: SqliteResource) -> None:
        self._settings = settings
        self._sqlite = sqlite
        self._extractor: Extractor | None = None
        self._unavailable_reason: str | None = None
        self._lock = asyncio.Lock()

    @property
    def unavailable_reason(self) -> str | None:
        """Human-readable reason the LLM is unavailable, or None when usable.

        Set after a failed `_ensure()`. Persists for the lifetime of the
        resource (we don't retry construction on every fetch).
        """
        return self._unavailable_reason

    async def _ensure(self) -> Extractor | None:
        """Construct the Extractor on first call; cached thereafter.

        Returns the cached instance on success, or `None` on permanent
        unavailability with `unavailable_reason` populated. Distinguishes
        config gaps from transient SDK errors — the latter propagate.
        """
        if self._extractor is not None:
            return self._extractor
        if self._unavailable_reason is not None:
            return None
        async with self._lock:
            if self._extractor is not None:
                return self._extractor
            if self._unavailable_reason is not None:
                return None
            self._extractor, self._unavailable_reason = await self._build()
            return self._extractor

    async def _build(self) -> tuple[Extractor | None, str | None]:
        """Construct an `Extractor` from settings; capture failure as reason.

        Provider selection runs through the plugin manifest registry
        (`_manifests/llm_providers/`). The `--auto` mode prefers claude-code
        when it's available and falls back to anthropic; explicit modes
        require the named provider to be in the registry.
        """
        try:
            from ._plugin import load_surface
            from .packages.llm_extract import ExtractionCache, Extractor, ModelSpec, Provider
        except Exception as exc:
            return None, f"llm module import failed: {exc}"

        s = self._settings
        registry = load_surface("a2web._manifests.llm_providers", Provider, s)

        # Auto: prefer claude-code, fall back to anthropic. Explicit modes
        # require the named provider to be in the registry.
        if s.llm_provider == "auto":
            order = ("claude-code", "anthropic")
        else:
            order = (s.llm_provider,)
        provider: Provider | None = None
        provider_id: str = ""
        for name in order:
            if name in registry:
                provider = registry[name]
                provider_id = name
                break
        if provider is None:
            missing = ", ".join(order)
            return None, f"no LLM provider available (tried: {missing}; configured: {sorted(registry)})"

        # Hook the extraction cache into the same sqlite file as the HTTP
        # cache. Ensures the underlying connection is open first.
        try:
            conn = await self._sqlite._ensure()
        except Exception as exc:  # sqlite open failure shouldn't block extraction
            cache: ExtractionCache | None = None
            del exc
        else:
            cache = ExtractionCache(conn, ttl_s=s.extraction_cache_ttl_s)

        from .packages.llm_extract.prompts import EXTRACT_CACHEABLE_V1

        extractor = Extractor(
            provider=provider,
            model=ModelSpec(provider_id, s.llm_model),
            template=EXTRACT_CACHEABLE_V1,
            max_content_chars=s.extraction_max_chars,
            cache=cache,
        )
        return extractor, None

    async def extract(
        self,
        *,
        content: str,
        ask: str,
        request_next_links: bool = False,
        handler_candidates: list[LlmNextLink] | None = None,
        max_content_chars: int | None = None,
        request_routing: bool = False,
    ) -> ExtractionResult | None:
        """Run extraction or return None when LLM is permanently unavailable.

        On None, caller should populate an OperatorHint from
        `unavailable_reason` and skip the extraction phase.

        `request_next_links` and `handler_candidates` opt into v0.7
        link-discovery Tier 2 output. `handler_candidates` is `list[LlmNextLink]`
        but typed as `list[Any]` here to avoid leaking the package boundary
        type onto the resource signature; the extractor enforces shape.

        `max_content_chars` overrides the extractor's per-call default for
        a single fetch (v0.10 harsh-test-session-fixes). `None` = use the
        extractor's configured default.
        """
        extractor = await self._ensure()
        if extractor is None:
            return None
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

    # Framework-facing async-CM protocol (a2kit v0.36+). Thin wrappers around
    # the existing idempotent `_ensure` / `close` internal surface.
    async def __aenter__(self) -> LlmExtractorResource:
        await self._ensure()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()


__all__ = ["LlmExtractorResource"]
