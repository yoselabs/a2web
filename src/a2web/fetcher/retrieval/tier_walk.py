"""The walk over TIER_ORDER, and the planner action executor it consults."""

from __future__ import annotations

import time
from enum import Enum

from ... import log as a2web_log
from ...actions import (
    Action,
    EscalateBrowser,
    EscalatePaid,
    PlannerCaps,
    RetryViaArchive,
    RewriteUrl,
    decide_next,
)
from ...decision_log import ObservationKind
from ...events import TierStarted
from ...models import CacheState, Diagnostic, Verdict
from ...state import AppState
from ...tiers import REGISTRY, TIER_ORDER, Tier, TierResult
from ..context import FetchContext, _within_budget
from ..retrieval.cookies import _phase_resolve_cookies
from ..retrieval.escalate.seam import Rung, escalate
from ..retrieval.install import TierInstall, install
from ..telemetry import _emit_tier_ended, _host

# Imported as MODULES, not names. `from .browser import _escalate_browser`
# freezes the reference at import time, so a test that fakes the rung would
# silently keep calling the real one — the same trap the dispatch table hit
# in §3.2, reintroduced by the file split. Attribute lookup happens at call
# time and stays fake-able.
from .escalate import archive as _archive_mod


class _Exec(Enum):
    """Outcome of executing a planner action — drives tier-loop control flow."""

    CONTINUE = "continue"  # advance to the next tier
    RESTART = "restart"  # URL was rewritten — restart the tier loop
    STOP = "stop"  # cascade done — a tier won or archive content installed


def _install_won_tier(
    fc: FetchContext,
    tier_result: TierResult,
    tier_name: str,
    tier: Tier,
) -> None:
    """Install winning tier content onto FetchContext.

    The tier observation is appended separately by the caller before the
    planner is consulted — this function only installs the content payload.
    """
    install(
        fc,
        TierInstall(
            body=tier_result.body,
            content_type=tier_result.content_type,
            final_url=tier_result.final_url,
            tier_used=tier_result.handler_name or (tier.name if hasattr(tier, "name") else tier_name),
            status_code=tier_result.status_code,
            pre_rendered=tier_result.pre_rendered,
        ),
    )
    fc.etag = tier_result.headers.get("etag")
    fc.last_modified = tier_result.headers.get("last-modified")
    # v0.7 link-discovery: thread Tier-1 candidates from the handler into fc.
    fc.next_links_handler = list(tier_result.next_links)
    # reddit-via-zyte content-expectations: carry a handler's measured counts.
    fc.comments_loaded = tier_result.comments_loaded
    fc.comments_total = tier_result.comments_total
    # Producer-declared cache volatility (None → `_ttl_for`'s heuristic).
    fc.volatility = tier_result.volatility
    # Listing sufficiency from a RENDERING handler: arxiv (and friends) already
    # compute "25 of 445" for their prose and used to discard both numbers, so
    # the sufficiency check — which only ever read the DOM record-miner's
    # output — never ran on the handler path at all. One assessment, two sources.
    if tier_result.items_rendered is not None:
        fc.record_count = tier_result.items_rendered
    if tier_result.items_advertised is not None:
        fc.regex_oracle_total = tier_result.items_advertised


def _planner_caps(fc: FetchContext) -> PlannerCaps:
    """Snapshot the per-fetch escalation budgets for the planner."""
    return PlannerCaps(
        url_rewrites=fc.url_rewrites,
        archive_dispatches=fc.archive_dispatches,
        browser_dispatches=fc.browser_dispatches,
        paid_dispatches=fc.paid_dispatches,
    )


def _tier_is_cloudflare(tier_result: TierResult) -> bool:
    """True when the tier response came through Cloudflare (server / cf-ray header)."""
    server = tier_result.headers.get("server", "").lower()
    return "cloudflare" in server or "cf-ray" in tier_result.headers


async def _dispatch_action(
    fc: FetchContext,
    action: Action,
    *,
    state: AppState,
    post_gate: bool,
) -> _Exec:
    """The single executor for every planner `Action` (unify-escalation-executor).

    Shared by the tier-walk (`post_gate=False`) and the post-gate escalation
    loop (`post_gate=True`). Handles the full 5-member `Action` union in one
    place — no action type is a silent no-op in a position where the planner can
    legally return it. Returns an `_Exec` control signal the caller interprets.

    The one genuine pipeline-region divergence (design D6) is the `RetryViaArchive`
    install: during the tier-walk the gate phase runs *later*, so archive installs
    the body only (`_install_archive_payload`, which observes a tier_outcome) and
    STOPs; post-gate the gate already ran, so archive installs the extracted
    fields (`_install_gate_archive`) and explicitly regates. `post_gate` selects
    the variant — this reflects the pipeline's real shape, not accidental
    coupling.

    `RewriteUrl` returns `_Exec.RESTART` (D2 — a first-class control outcome the
    tier loop consumes to restart the walk); the planner does not return it
    post-gate (asserted by test), so the caller there never acts on it.
    """
    if isinstance(action, RewriteUrl):
        fc.url_rewrites += 1
        fc.url = action.new_url
        fc.final_url = fc.url
        fc.cached_row = await fc.sqlite.get(fc.url, fc.profile_hash) if fc.sqlite is not None else None
        return _Exec.RESTART

    if isinstance(action, RetryViaArchive):
        if post_gate:
            # Post-gate archive goes through the one escalation seam, which
            # comprehends what it installs. The pre-gate walk below does not need
            # to: `_phase_extract` runs next and comprehends everything.
            await escalate(fc, Rung.archive, state=state)
            return _Exec.CONTINUE  # post-gate loop reconsults decide_next
        fc.archive_dispatches += 1
        outcome = await _archive_mod._dispatch_archive(
            action.url,
            state=state,
            start_perf=fc.start_perf,
            diagnostics=fc.diagnostics,
        )
        if outcome.success:
            _archive_mod._install_archive_payload(fc, outcome)
            return _Exec.STOP
        return _Exec.CONTINUE  # archive failed → caller decides tier-win / advance

    if isinstance(action, EscalateBrowser):
        await escalate(fc, Rung.browser, state=state)
        return _Exec.CONTINUE

    if isinstance(action, EscalatePaid):
        await escalate(fc, Rung.paid, state=state)
        return _Exec.CONTINUE

    # Continue — no escalation. The tier-walk caller decides won-tier install /
    # advance; the post-gate caller ends the loop.
    return _Exec.CONTINUE


async def _phase_tier_loop(fc: FetchContext, *, state: AppState) -> None:
    """Walk TIER_ORDER, dispatch each tier, run after-tier actions, until one wins or all fail.

    Supports two interruptions of the linear flow:
    - `RewriteUrl` from after-tier action → restart the loop with the new URL (cap=1).
    - `RetryViaArchive` from after-tier action → out-of-band archive dispatch (cap=1).
    """
    proxy_pool = state.proxy_pool

    # v0.8: resolve cookies for the current host before any tier dispatch.
    # No-op when cookie_source == "none" or no jar was provisioned.
    await _phase_resolve_cookies(fc, state=state)

    while True:
        restart_loop = False
        # If a previous iteration rewrote the URL to a new host, re-resolve.
        await _phase_resolve_cookies(fc, state=state)
        for tier_name in TIER_ORDER:
            tier = REGISTRY[tier_name]
            tier_start_ms = int((time.perf_counter() - fc.start_perf) * 1000)

            conditional_extras: dict[str, str] | None = None
            if fc.cached_row is not None:
                conditional_extras = {}
                if fc.cached_row.etag:
                    conditional_extras["etag"] = fc.cached_row.etag
                if fc.cached_row.last_modified:
                    conditional_extras["last_modified"] = fc.cached_row.last_modified

            handle = proxy_pool.acquire(_host(fc.url) or "", tier_name)
            if handle is None:
                fc.diagnostics.append(
                    Diagnostic(
                        t_ms=tier_start_ms,
                        step=tier_name,
                        engine=None,
                        host=_host(fc.url),
                        proxy=None,
                        verdict=Verdict.proxy_unavailable,
                        dur_ms=0,
                        extra={"reason": "all_proxies_dead_required"},
                    )
                )
                fc.observe(kind=ObservationKind.tier_outcome, source=tier_name, verdict=Verdict.proxy_unavailable)
                continue

            await a2web_log.info(TierStarted(t_ms=tier_start_ms, step=tier_name, host=_host(fc.url)))

            async with _within_budget(fc, about_to=f"tier:{tier_name}"):
                tier_result = await tier.fetch(
                    fc.url,
                    state=state,
                    proxy_url=handle.proxy_url,
                    conditional_extras=conditional_extras,
                    cookies=fc.cookies,
                    cookies_full=fc.cookies_full,
                )

            # Silent skip — no diagnostic row
            if tier_result.no_match or tier_result.skipped:
                continue

            proxy_pool.report(
                handle,
                success=tier_result.verdict not in (Verdict.proxy_unavailable, Verdict.connection_error, Verdict.timeout),
            )

            tier_dur_ms = await _emit_tier_ended(
                step=tier_result.handler_name or tier_name,
                engine="curl_cffi" if tier_name == "raw" else None,
                verdict=tier_result.verdict,
                start_ms=tier_start_ms,
                start_perf=fc.start_perf,
                extra={
                    "status_code": tier_result.status_code,
                    "route.proxy_id": handle.proxy_id,
                    "route.matched_rule": str(handle.matched_rule_index) if handle.matched_rule_index is not None else "none",
                },
            )

            # Conditional 304 → reuse cached body. Distinct return path (no
            # after-tier action, no further tiers, no extract/gate ahead).
            if tier_result.status_code == 304 and fc.cached_row is not None and tier_result.conditional_hit:
                fc.body = fc.cached_row.body
                fc.content_type = fc.cached_row.content_type or "text/html"
                fc.status_code = 200  # logical hit
                fc.cache_state = CacheState.hit
                fc.etag = fc.cached_row.etag
                fc.last_modified = fc.cached_row.last_modified
                fc.tier_used = tier_name
                fc.observe(kind=ObservationKind.tier_outcome, source=tier_name, verdict=Verdict.ok)
                fc.diagnostics.append(
                    Diagnostic(
                        t_ms=tier_start_ms,
                        step=tier_name,
                        engine="curl_cffi",
                        host=_host(fc.url),
                        proxy=handle.proxy_id,
                        verdict=Verdict.ok,
                        dur_ms=tier_dur_ms,
                        extra={"conditional_hit": "true"},
                    )
                )
                return

            fc.diagnostics.append(
                Diagnostic(
                    t_ms=tier_start_ms,
                    step=tier_name,
                    engine="curl_cffi" if tier_name == "raw" else None,
                    host=_host(tier_result.final_url),
                    proxy=handle.proxy_id,
                    verdict=tier_result.verdict,
                    dur_ms=tier_dur_ms,
                    extra={"status_code": tier_result.status_code},
                )
            )

            # Escalate to a paid site render: a converting handler's rewritten
            # fetch failed (HN's Algolia API), or a walled surface (Reddit
            # search 403) can only be read by rendering the real page. The
            # diagnostic above records the failed attempt; here we log a
            # NON-authoritative observation, flag the fetch for a direct paid
            # render, and STOP the free ladder — raw/jina would get fooled by the
            # SPA shell (which can exceed the length floor) or the block page. The
            # gate/escalate phase dispatches the paid tier onto the original URL.
            if tier_result.escalate_to_render:
                fc.observe(
                    kind=ObservationKind.tier_outcome,
                    source=tier_result.handler_name or tier_name,
                    verdict=tier_result.verdict,
                    authoritative=False,
                    status_code=tier_result.status_code,
                    cloudflare=False,
                )
                fc.render_requested = True
                return  # stop the free ladder; the paid render happens in gate/escalate

            # Append the tier observation BEFORE consulting the planner, so
            # `decide_next` sees the full decision log; then execute its action.
            authoritative = tier_name == "site_handler" and tier_result.verdict is Verdict.not_found
            fc.observe(
                kind=ObservationKind.tier_outcome,
                source=tier_result.handler_name or tier_name,
                verdict=tier_result.verdict,
                authoritative=authoritative,
                status_code=tier_result.status_code,
                cloudflare=_tier_is_cloudflare(tier_result),
                subresource_blocks=tier_result.subresource_blocks,
            )
            # Propagate a handler-set operator hint into fc so it reaches the
            # response. Previously only the browser escalation consumed
            # `TierResult.operator_hint`; site handlers (e.g. reddit's eager
            # `try_user_browser`) had no path to the wire.
            if tier_result.operator_hint is not None:
                fc.operator_hints.append(tier_result.operator_hint)
            action = decide_next(fc.observations, url=fc.url, caps=_planner_caps(fc))
            executed = await _dispatch_action(fc, action, state=state, post_gate=False)
            if executed is _Exec.RESTART:
                restart_loop = True
                break  # break inner for; while True restarts
            if executed is _Exec.STOP:
                return  # archive content installed
            # A transport/status failure now escalates to the browser mid-walk
            # (escalate-on-status-derived-walls). When that out-of-band render
            # installs a gate-passing result, end the walk on it rather than
            # advancing to — and clobbering it with — the next free tier. A
            # normal won tier has not set `tier_used` yet (that happens just
            # below), so this only catches an already-installed escalation win.
            if fc.tier_used != "none" and fc.resolved_verdict() is Verdict.ok:
                return
            # _Exec.CONTINUE → the planner did not stop the walk. Install a
            # winning tier's content and finish; otherwise advance to the next
            # tier. (The won-tier install lives here, not in the dispatcher — it
            # is keyed on the tier result, not on a planner Action.)
            if tier_result.verdict is Verdict.ok:
                _install_won_tier(fc, tier_result, tier_name, tier)
                return
            # tier lost → next tier

        if not restart_loop:
            return
