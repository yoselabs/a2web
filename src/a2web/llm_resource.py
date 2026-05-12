"""LlmExtractorResource — lazy-init Extractor wrapper for AppState.

Resource pattern (a2kit v0.27 canonical): sync __init__, async _ensure
under internal lock, non-Optional on AppState. The underlying Extractor
is constructed on first use because the `anthropic`/`claude-agent-sdk`
SDKs are optional deps behind the `[llm]` install extra — bare a2web
installs must not crash on import.

Provider selection follows `settings.llm_provider`:
- ``auto``         — try ClaudeCode (OS session via `claude-agent-sdk`)
                     first; fall back to Anthropic API.
- ``anthropic``    — direct Anthropic Messages API; requires API key.
- ``claude-code``  — Claude Code OS session only.

The `_ensure()` contract returns `None` on permanent unavailability
(missing extra, missing API key, no provider usable). Transient SDK
errors propagate normally. Callers branch on the None return and
populate an OperatorHint without retrying construction.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .packages.llm_extract import LLMNotAvailable
from .settings import AppSettings

if TYPE_CHECKING:
    from .packages.http_cache import SqliteResource
    from .packages.llm_extract import ExtractionResult, Extractor


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
        """Construct an `Extractor` from settings; capture failure as reason."""
        try:
            from .packages.llm_extract import ExtractionCache, Extractor, ModelSpec
            from .packages.llm_extract.providers.anthropic import AnthropicProvider
            from .packages.llm_extract.providers.claude_code import ClaudeCodeProvider
        except Exception as exc:
            return None, f"llm module import failed: {exc}"

        s = self._settings
        provider_id = s.llm_provider
        provider: AnthropicProvider | ClaudeCodeProvider | None = None
        attempt_errors: list[str] = []

        if provider_id in ("claude-code", "auto"):
            try:
                provider = ClaudeCodeProvider()
                provider_id = "claude-code"
            except LLMNotAvailable as exc:
                if s.llm_provider == "claude-code":
                    return None, str(exc)
                attempt_errors.append(f"claude-code: {exc}")

        if provider is None and provider_id in ("anthropic", "auto"):
            try:
                provider = AnthropicProvider(api_key_env=s.llm_api_key_env)
                provider_id = "anthropic"
            except LLMNotAvailable as exc:
                attempt_errors.append(f"anthropic: {exc}")

        if provider is None:
            return None, "no LLM provider available. " + "; ".join(attempt_errors)

        # Hook the extraction cache into the same sqlite file as the HTTP
        # cache. Ensures the underlying connection is open first.
        try:
            conn = await self._sqlite._ensure()
        except Exception as exc:  # sqlite open failure shouldn't block extraction
            cache: ExtractionCache | None = None
            del exc
        else:
            cache = ExtractionCache(conn, ttl_s=s.extraction_cache_ttl_s)

        extractor = Extractor(
            provider=provider,
            model=ModelSpec(provider_id, s.llm_model),
            max_content_chars=s.extraction_max_chars,
            cache=cache,
        )
        return extractor, None

    async def extract(self, *, content: str, ask: str) -> ExtractionResult | None:
        """Run extraction or return None when LLM is permanently unavailable.

        On None, caller should populate an OperatorHint from
        `unavailable_reason` and skip the extraction phase.
        """
        extractor = await self._ensure()
        if extractor is None:
            return None
        return await extractor.extract(content=content, ask=ask)

    async def close(self) -> None:
        """No-op today; symmetric with sqlite/browser for lifecycle hooks."""
        return None


__all__ = ["LlmExtractorResource"]
