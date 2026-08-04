"""Cookie resolution for the current host, and the staleness hint."""

from __future__ import annotations

import time
from urllib.parse import urlparse

from ... import log as a2web_log
from ...events.types import CookiesAttached, CookiesStale
from ...hints import (
    cookies_stale_hint,
)
from ...state import AppState, ResourceUnavailable
from ..context import FetchContext
from ..telemetry import _format_age

# --------------------------------------------------------------------- #
# Cookie resolution + staleness phases (v0.8)
# --------------------------------------------------------------------- #


async def _phase_resolve_cookies(fc: FetchContext, *, state: AppState) -> None:
    """Resolve cookies for the current fetch host into FetchContext.

    No-op when `cookie_source == "none"` or when the cookie_jar Lazy is an
    unavailable stub (caller didn't provision one). Re-resolves when
    `fc.url`'s host has changed since the last call (e.g. after `RewriteUrl`).
    Emits a redacted `CookiesAttached` event on a non-empty resolution.
    """
    if state.settings.cookie_source == "none":
        return

    parsed = urlparse(fc.url)
    host = parsed.hostname or ""
    if not host:
        return
    if fc.cookies_resolved_for_host == host:
        return  # already resolved for this host this fetch
    scheme = parsed.scheme or "https"
    path = parsed.path or "/"

    try:
        jar = await fc.resources.cookie_jar()
    except ResourceUnavailable:
        return
    cookies_full = await jar.get_for_host(host, scheme, path)
    fc.cookies_full = cookies_full
    fc.cookies = {c.name: c.value for c in cookies_full}
    fc.cookies_resolved_for_host = host

    if cookies_full:
        t_ms = int((time.perf_counter() - fc.inputs.start_perf) * 1000)
        await a2web_log.info(
            CookiesAttached(
                t_ms=t_ms,
                host=host,
                cookie_count=len(cookies_full),
                cookie_names=[c.name for c in cookies_full],
            ),
        )


async def _phase_cookies_staleness(fc: FetchContext, *, state: AppState) -> None:
    """Append the `cookies_stale` operator hint and log event when stale.

    Idempotent within a fetch: `fc.cookies_stale_hint_appended` flips on the
    first append, preventing a duplicate after `RewriteUrl` restarts.
    """
    if state.settings.cookie_source == "none":
        return
    if fc.cookies_stale_hint_appended:
        return
    try:
        jar = await fc.resources.cookie_jar()
    except ResourceUnavailable:
        return
    info = await jar.staleness()
    if not info.is_stale:
        return
    threshold_h = state.settings.cookie_stale_after_hours
    age_str = _format_age(info.age_hours)
    fc.operator_hints.append(cookies_stale_hint(age=age_str, threshold_hours=threshold_h))
    t_ms = int((time.perf_counter() - fc.inputs.start_perf) * 1000)
    await a2web_log.info(
        CookiesStale(
            t_ms=t_ms,
            profile=state.settings.cookie_profile,
            browser=str(state.settings.cookie_source),
            age_hours=info.age_hours if info.age_hours is not None else -1.0,
            threshold_hours=threshold_h,
        ),
    )
    fc.cookies_stale_hint_appended = True
