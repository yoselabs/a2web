"""TTL policy, the cache read, the cache write."""

from __future__ import annotations

import time

from ... import log as a2web_log
from ...events import StageEnded, StageStarted
from ...models import CacheState, Verdict
from ...settings import AppSettings
from ...state import AppState
from ..context import FetchContext


def _ttl_for(content_type: str | None, settings: AppSettings, *, volatility: str | None = None) -> int:
    """Cache TTL in seconds: the PRODUCER'S declaration first, heuristic second.

    A handler serving an upstream API knows what the content-type cannot say.
    `application/json` from the GitHub issues API is a live discussion;
    `application/json` from a CDN may be a static asset. The heuristic saw only
    "not html" and gave both the 168-hour static TTL, so every handler-served
    thread, issue list and listing was cached for SEVEN DAYS — the freshest
    surfaces in the product, held the longest.

    `settings` is typed `AppSettings`, not `object`, and reads attributes
    directly. It previously used `getattr(settings_obj, "cache_ttl_article_h", 24)`,
    which duplicated every default and would have silently kept serving the
    literal through a settings rename instead of failing.
    """
    if volatility is not None:
        return {
            "live": settings.cache_ttl_live_m * 60,
            "article": settings.cache_ttl_article_h * 3600,
            "static": settings.cache_ttl_static_h * 3600,
        }[volatility]
    ct = (content_type or "").lower()
    if "html" in ct:
        return settings.cache_ttl_article_h * 3600
    return settings.cache_ttl_static_h * 3600


# --------------------------------------------------------------------- #
# Phase functions
# --------------------------------------------------------------------- #


async def _phase_cache_check(fc: FetchContext) -> None:
    """Read the cached row (if cache is enabled and a hit exists)."""
    if fc.resources.sqlite is not None:
        fc.cached_row = await fc.resources.sqlite.get(fc.url, fc.inputs.profile_hash)


async def _phase_cache_write(fc: FetchContext, *, state: AppState) -> None:
    """Write to cache iff gate passed, non-hit, non-bypass, non-archive."""
    is_archive_result = fc.tier_used == "archive"
    should_cache = (
        fc.resources.sqlite is not None
        and not fc.inputs.bypass_cache
        and fc.cache_state != CacheState.hit
        and fc.resolved_verdict() is Verdict.ok
        and fc.body
        and not is_archive_result
    )
    if not should_cache:
        return
    assert fc.resources.sqlite is not None  # noqa: S101 — narrowed by should_cache

    cache_dur_start = int((time.perf_counter() - fc.inputs.start_perf) * 1000)
    await a2web_log.info(StageStarted(t_ms=cache_dur_start, step="cache_write"))
    await fc.resources.sqlite.put(
        fc.url,
        fc.inputs.profile_hash,
        etag=fc.etag,
        last_modified=fc.last_modified,
        status_code=fc.status_code,
        content_type=fc.content_type,
        body=fc.body,
        ttl_s=_ttl_for(fc.content_type, state.settings, volatility=fc.volatility),
    )
    cache_dur_ms = int((time.perf_counter() - fc.inputs.start_perf) * 1000) - cache_dur_start
    await a2web_log.info(
        StageEnded(t_ms=cache_dur_start, step="cache_write", verdict=Verdict.ok, dur_ms=cache_dur_ms),
    )
