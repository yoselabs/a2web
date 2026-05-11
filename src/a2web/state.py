"""Per-App shared state — typed DI container for long-lived resources.

`AppState` carries the resource handles tools and tiers depend on. Lifecycle is
owned by a2kit v0.26+ via `@app.on_startup` / `@app.on_shutdown` hooks plus
`app.singleton(AppState, factory=build_state)` — see `server.py` for the wiring.

Browser pool stays lazily opened inside `BrowserTier.fetch` (Camoufox is an
optional dep; we must not crash startup if it's missing).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiosqlite
from purgatory import AsyncCircuitBreakerFactory

from .log.writer import LogWriter
from .proxy.pool import ProxyPool
from .settings import AppSettings, get_settings

if TYPE_CHECKING:
    from .browser.pool import BrowserPool
    from .llm import Extractor


@dataclass(slots=True)
class AppState:
    """Shared resources for the fetch pipeline. Per-App singleton.

    `sqlite` is assigned by the `@app.on_startup` hook (requires event loop).
    `browser_pool` stays None and is lazily opened on first browser-tier
    dispatch (Camoufox is an optional dep). `llm_extractor` stays None and
    is lazily constructed on the first `ask=`-bearing fetch (the
    `anthropic` SDK is also an optional dep).
    """

    settings: AppSettings
    breakers: AsyncCircuitBreakerFactory
    log_writer: LogWriter
    proxy_pool: ProxyPool
    sqlite: aiosqlite.Connection | None = None
    browser_pool: BrowserPool | None = None
    browser_lock: asyncio.Lock | None = None
    llm_extractor: Extractor | None = None
    llm_lock: asyncio.Lock | None = None
    llm_unavailable_reason: str | None = None  # set when construction fails


def build_state(settings: AppSettings | None = None) -> AppState:
    """Factory for the AppState singleton. Sqlite is opened in @on_startup."""
    resolved = settings or get_settings()
    return AppState(
        settings=resolved,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        log_writer=LogWriter(disabled=not resolved.log_enabled),
        proxy_pool=ProxyPool(settings=resolved),
    )


async def ensure_browser_pool(state: AppState):
    """Open Camoufox pool on first call; return cached pool thereafter.

    Stays lazy because Camoufox is an optional dep — opening at startup would
    crash apps that don't have the [browser] extras installed. ImportError
    propagates to the caller (BrowserTier translates to a graceful operator
    hint).
    """
    if state.browser_pool is not None:
        return state.browser_pool
    if state.browser_lock is None:
        state.browser_lock = asyncio.Lock()
    async with state.browser_lock:
        if state.browser_pool is None:
            from .browser.pool import BrowserPool  # local — optional dep

            pool = BrowserPool(
                max_pool=state.settings.browser_max_pool,
                idle_timeout_s=state.settings.browser_idle_timeout_s,
                page_budget_s=state.settings.browser_page_budget_s,
            )
            await pool.start()
            state.browser_pool = pool
    return state.browser_pool


async def ensure_llm_extractor(state: AppState):
    """Construct an Extractor on first ask=-bearing fetch; cache thereafter.

    Returns the cached Extractor on success, or None if construction failed
    (missing `[llm]` extra OR missing API key OR otherwise unconfigured).
    On failure, `state.llm_unavailable_reason` records the human-readable
    reason so the orchestrator can populate operator_hints.

    Lazy because the `anthropic` SDK is an optional dep and we don't want a
    bare a2web install to crash on import. The factory is settings-driven —
    `llm_provider` chooses the backend, `llm_model` chooses the model id.
    """
    if state.llm_extractor is not None:
        return state.llm_extractor
    if state.llm_unavailable_reason is not None:
        return None  # already failed once; don't retry every fetch
    if state.llm_lock is None:
        state.llm_lock = asyncio.Lock()
    async with state.llm_lock:
        if state.llm_extractor is not None:
            return state.llm_extractor
        if state.llm_unavailable_reason is not None:
            return None
        try:
            from .llm import ExtractionCache, Extractor, ModelSpec
            from .llm.errors import LLMNotAvailable
            from .llm.providers.anthropic import AnthropicProvider
            from .llm.providers.claude_code import ClaudeCodeProvider

            s = state.settings
            provider_id = s.llm_provider
            provider: AnthropicProvider | ClaudeCodeProvider | None = None
            attempt_errors: list[str] = []

            if provider_id in ("claude-code", "auto"):
                try:
                    provider = ClaudeCodeProvider()
                    provider_id = "claude-code"
                except LLMNotAvailable as exc:
                    if s.llm_provider == "claude-code":
                        state.llm_unavailable_reason = str(exc)
                        return None
                    attempt_errors.append(f"claude-code: {exc}")

            if provider is None and provider_id in ("anthropic", "auto"):
                try:
                    provider = AnthropicProvider(api_key_env=s.llm_api_key_env)
                    provider_id = "anthropic"
                except LLMNotAvailable as exc:
                    attempt_errors.append(f"anthropic: {exc}")

            if provider is None:
                state.llm_unavailable_reason = (
                    "no LLM provider available. " + "; ".join(attempt_errors)
                )
                return None

            # Hook the extraction cache into the same sqlite file as the
            # HTTP cache. When sqlite isn't yet open (early test), the
            # extractor runs uncached — cache is purely an optimization.
            cache = None
            if state.sqlite is not None:
                cache = ExtractionCache(state.sqlite, ttl_s=s.extraction_cache_ttl_s)

            state.llm_extractor = Extractor(
                provider=provider,
                model=ModelSpec(provider_id, s.llm_model),
                max_content_chars=s.extraction_max_chars,
                cache=cache,
            )
            return state.llm_extractor
        except Exception as exc:
            state.llm_unavailable_reason = f"llm_extractor construction failed: {exc}"
            return None
