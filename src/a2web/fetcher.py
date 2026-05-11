"""Fetch orchestrator — cache check → tier loop → extract → gate → cache write.

The orchestrator is the only place tier order is encoded. Tiers themselves
are pure-ish (HTTP I/O only); extraction is sync libraries via async
chokepoints; the gate is a pure function. Block pages NEVER enter the
cache (gate verdict gates the write).

State for one fetch lives in a `FetchContext` dataclass. The pipeline is a
sequence of named phase functions that mutate fields on it; the top-level
`_run_pipeline` is a thin coordinator.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import a2kit
import aiosqlite
import structlog

from .actions import RetryViaArchive, RewriteUrl, next_action_after_gate, next_action_after_tier
from .cache.sqlite_cache import (
    CacheRow,
    cache_get,
    cache_put,
    compute_profile_hash,
    is_live_only,
)
from .events import StageEnded, StageStarted, TierEnded, TierStarted
from .extract.metadata import parse_metadata
from .extract.trafilatura_ext import extract_markdown
from .gate.block_detector import evaluate
from .log.record import from_response as record_from_response
from .models import (
    CacheState,
    Confidence,
    Diagnostic,
    FetchResponse,
    FetchStatus,
    Heading,
    Link,
    OperatorHint,
    TokenCounts,
    Verdict,
)
from .state import AppState
from .tiers import REGISTRY, TIER_ORDER, Rendered
from .tiers.jina import JinaTier
from .tiers.raw import RawTier
from .utils.time import fmt_dur


def _ttl_for(content_type: str | None, settings_obj: object) -> int:
    """Pick a TTL in seconds based on a coarse content-type heuristic."""
    ct = (content_type or "").lower()
    if "html" in ct:
        return getattr(settings_obj, "cache_ttl_article_h", 24) * 3600
    return getattr(settings_obj, "cache_ttl_static_h", 168) * 3600


def _confidence_for(verdict: Verdict, content_md: str) -> Confidence:
    if verdict != Verdict.ok:
        return Confidence.low
    if len(content_md) > 2000:
        return Confidence.high
    return Confidence.medium


_LOG = structlog.get_logger("a2web")


@dataclass(slots=True)
class FetchContext:
    """Mutable per-fetch state passed between phase functions.

    Replaces the v0.1 pattern of 20+ local variables in `_run_pipeline`.
    Phase functions read and write fields here; the top-level coordinator
    constructs one, runs the phases, and builds the response from it.
    """

    # Inputs (set at construction; not mutated by phases)
    started_at: datetime
    start_perf: float
    profile_hash: str
    sqlite_conn: aiosqlite.Connection | None
    bypass_cache: bool

    # URL state (rewritten on after-tier RewriteUrl)
    url: str
    final_url: str

    # Body & verdict state (set by tier loop, mutated by escalations)
    body: bytes = b""
    content_type: str = ""
    status_code: int = 0
    tier_used: str = "none"
    final_verdict: Verdict = Verdict.other
    etag: str | None = None
    last_modified: str | None = None
    pre_rendered_payload: Rendered | None = None

    # Cache state
    cache_state: CacheState = CacheState.miss
    cached_row: CacheRow | None = None

    # Per-fetch escalation caps
    url_rewrites: int = 0
    archive_dispatches: int = 0
    browser_dispatches: int = 0

    # Extraction outputs
    content_md: str = ""
    title: str | None = None
    byline: str | None = None
    published: date | None = None
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    meta_dict: dict[str, str] = field(default_factory=dict)

    # Gate state
    gate_verdict: Verdict = Verdict.ok
    gate_subsystem: str | None = None
    browser_unavailable_hint: OperatorHint | None = None

    # Diagnostics accumulator
    diagnostics: list[Diagnostic] = field(default_factory=list)


async def fetch(url: str, *, state: AppState, ctx: a2kit.ToolContext | None = None) -> FetchResponse:
    """Run the v0.1 cascade for one URL.

    `ctx` is the a2kit ToolContext; when supplied, the orchestrator emits
    typed phase-boundary events via `a2kit.ldd.event(ctx, ...)`. When None
    (direct calls from unit tests), no events are emitted. a2kit's emission
    chain owns the wire bridge + OTel sink fan-out.
    """
    start_perf = time.perf_counter()
    started_at = datetime.now(UTC)

    profile_hash = compute_profile_hash(state.settings)
    bypass_cache = is_live_only(url, state.settings)
    sqlite_conn = None if bypass_cache else state.sqlite

    fc = FetchContext(
        started_at=started_at,
        start_perf=start_perf,
        profile_hash=profile_hash,
        sqlite_conn=sqlite_conn,
        bypass_cache=bypass_cache,
        url=url,
        final_url=url,
        cache_state=CacheState.bypass if bypass_cache else CacheState.miss,
    )

    response = await _run_pipeline(fc, state=state, ctx=ctx)

    if state.log_writer is not None:
        try:
            await state.log_writer.write_record(record_from_response(response, input_url=url))
        except Exception as exc:
            response.operator_hints.append(OperatorHint(code="log_write_failed", message=str(exc)))
            _LOG.warning("log_write_failed", error=str(exc), url=url)

    return response


# --------------------------------------------------------------------- #
# Event emission helpers
# --------------------------------------------------------------------- #

async def _emit(ctx: a2kit.ToolContext | None, event) -> None:
    """Emit a typed event via a2kit.ldd, no-op when ctx is None."""
    if ctx is None:
        return
    await a2kit.ldd.event(ctx, event.__class__.__name__, **_event_payload(event))


def _event_payload(event) -> dict:
    """Flatten a dataclass event into kwargs for a2kit.ldd.event."""
    payload: dict[str, object] = {"t_ms": event.t_ms, "step": event.step}
    if isinstance(event, TierEnded | StageEnded):
        payload["verdict"] = event.verdict.value
        payload["dur_ms"] = event.dur_ms
        if getattr(event, "extra", None):
            payload["extra"] = event.extra
    if isinstance(event, TierStarted):
        if event.engine:
            payload["engine"] = event.engine
        if event.host:
            payload["host"] = event.host
        if event.proxy:
            payload["proxy"] = event.proxy
    if isinstance(event, TierEnded) and event.engine:
        payload["engine"] = event.engine
    return payload


# --------------------------------------------------------------------- #
# Archive escalation helper (shared by after-tier + after-gate)
# --------------------------------------------------------------------- #

@dataclass(slots=True)
class _ArchiveOutcome:
    """Result of one archive-tier dispatch — used by `_dispatch_archive`."""

    success: bool
    body: bytes = b""
    content_type: str = ""
    final_url: str = ""
    pre_rendered: Rendered | None = None
    status_code: int = 0


async def _dispatch_archive(
    url: str,
    *,
    state: AppState,
    ctx: a2kit.ToolContext | None,
    start_perf: float,
    diagnostics: list[Diagnostic],
) -> _ArchiveOutcome:
    """One-stop archive dispatch — used by both after-tier and after-gate paths.

    Emits TierStarted/TierEnded around the archive fetch, appends a Diagnostic
    only on success (a failed escalation is "tried, didn't help" and should
    not displace the originating verdict), and returns an outcome the caller
    installs into orchestrator state.
    """
    archive_tier = REGISTRY["archive"]
    arch_start_ms = int((time.perf_counter() - start_perf) * 1000)
    await _emit(ctx, TierStarted(t_ms=arch_start_ms, step="archive", host=_host(url)))
    archive_result = await archive_tier.fetch(url, state=state)
    arch_dur_ms = int((time.perf_counter() - start_perf) * 1000) - arch_start_ms
    engine = archive_result.archive_source or "archive"
    await _emit(
        ctx,
        TierEnded(
            t_ms=arch_start_ms,
            step="archive",
            engine=engine,
            verdict=archive_result.verdict,
            dur_ms=arch_dur_ms,
            extra={"status_code": archive_result.status_code},
        ),
    )
    archive_pre = archive_result.pre_rendered
    if archive_result.verdict != Verdict.ok or archive_pre is None:
        return _ArchiveOutcome(success=False)
    diagnostics.append(
        Diagnostic(
            t_ms=arch_start_ms,
            step="archive",
            engine=engine,
            host=_host(url),
            proxy=None,
            verdict=archive_result.verdict,
            dur_ms=arch_dur_ms,
            extra={"status_code": archive_result.status_code},
        )
    )
    return _ArchiveOutcome(
        success=True,
        body=archive_result.body,
        content_type=archive_result.content_type,
        final_url=archive_result.final_url,
        pre_rendered=archive_pre,
        status_code=archive_result.status_code,
    )


# --------------------------------------------------------------------- #
# Phase functions
# --------------------------------------------------------------------- #

async def _phase_cache_check(fc: FetchContext) -> None:
    """Read the cached row (if cache is enabled and a hit exists)."""
    if fc.sqlite_conn is not None:
        fc.cached_row = await cache_get(fc.sqlite_conn, fc.url, fc.profile_hash)


async def _phase_tier_loop(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext | None) -> None:
    """Walk TIER_ORDER, dispatch each tier, run after-tier actions, until one wins or all fail.

    Supports two interruptions of the linear flow:
    - `RewriteUrl` from after-tier action → restart the loop with the new URL (cap=1).
    - `RetryViaArchive` from after-tier action → out-of-band archive dispatch (cap=1).
    """
    proxy_pool = state.proxy_pool

    while True:
        restart_loop = False
        archive_break_payload: dict | None = None
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
                fc.final_verdict = Verdict.proxy_unavailable
                continue

            await _emit(ctx, TierStarted(t_ms=tier_start_ms, step=tier_name, host=_host(fc.url)))

            if isinstance(tier, RawTier):
                tier_result = await tier.fetch(
                    fc.url,
                    state=state,
                    conditional_extras=conditional_extras,
                    proxy_url=handle.proxy_url,
                )
            elif isinstance(tier, JinaTier):
                tier_result = await tier.fetch(fc.url, state=state, proxy_url=handle.proxy_url)
            else:
                tier_result = await tier.fetch(fc.url, state=state)

            tier_dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - tier_start_ms

            # Silent skip — no diagnostic row
            if tier_result.no_match or tier_result.skipped:
                continue

            proxy_pool.report(
                handle,
                success=tier_result.verdict not in (Verdict.proxy_unavailable, Verdict.connection_error, Verdict.timeout),
                ms=tier_dur_ms,
            )

            await _emit(
                ctx,
                TierEnded(
                    t_ms=tier_start_ms,
                    step=tier_result.handler_name or tier_name,
                    engine="curl_cffi" if tier_name == "raw" else None,
                    verdict=tier_result.verdict,
                    dur_ms=tier_dur_ms,
                    extra={
                        "status_code": tier_result.status_code,
                        "route.proxy_id": handle.proxy_id,
                        "route.matched_rule": str(handle.matched_rule_index) if handle.matched_rule_index is not None else "none",
                    },
                ),
            )

            # Conditional 304 → reuse cached body
            if tier_result.status_code == 304 and fc.cached_row is not None and tier_result.conditional_hit:
                fc.body = fc.cached_row.body
                fc.content_type = fc.cached_row.content_type or "text/html"
                fc.status_code = 200  # logical hit
                fc.cache_state = CacheState.hit
                fc.etag = fc.cached_row.etag
                fc.last_modified = fc.cached_row.last_modified
                fc.tier_used = tier_name
                fc.final_verdict = Verdict.ok
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

            # After-tier action: URL rewrite or archive escalation
            tier_action = next_action_after_tier(tier_result, fc.url, state.settings)
            if isinstance(tier_action, RewriteUrl) and fc.url_rewrites < 1:
                fc.url_rewrites += 1
                fc.url = tier_action.new_url
                fc.final_url = fc.url
                # Reset cached_row — new URL likely has its own cache entry.
                if fc.sqlite_conn is not None:
                    fc.cached_row = await cache_get(fc.sqlite_conn, fc.url, fc.profile_hash)
                else:
                    fc.cached_row = None
                restart_loop = True
                break  # break inner for; while True continues
            if isinstance(tier_action, RetryViaArchive) and fc.archive_dispatches < 1:
                fc.archive_dispatches += 1
                outcome = await _dispatch_archive(
                    tier_action.url, state=state, ctx=ctx, start_perf=fc.start_perf, diagnostics=fc.diagnostics,
                )
                if outcome.success:
                    archive_break_payload = {
                        "body": outcome.body,
                        "content_type": outcome.content_type,
                        "final_url": outcome.final_url,
                        "pre_rendered": outcome.pre_rendered,
                        "status_code": outcome.status_code,
                    }
                    break
                # Archive failed — keep trying tiers (fallthrough).

            if tier_result.verdict == Verdict.ok:
                fc.body = tier_result.body
                fc.content_type = tier_result.content_type
                fc.status_code = tier_result.status_code
                fc.final_url = tier_result.final_url
                fc.tier_used = tier_result.handler_name or (tier.name if hasattr(tier, "name") else tier_name)
                fc.final_verdict = Verdict.ok
                fc.etag = tier_result.headers.get("etag")
                fc.last_modified = tier_result.headers.get("last-modified")
                fc.pre_rendered_payload = tier_result.pre_rendered
                break

            fc.final_verdict = tier_result.verdict

        # If after-tier dispatch landed archive content, install it.
        if archive_break_payload is not None:
            fc.body = archive_break_payload["body"]
            fc.content_type = archive_break_payload["content_type"]
            fc.final_url = archive_break_payload["final_url"]
            fc.tier_used = "archive"
            fc.pre_rendered_payload = archive_break_payload["pre_rendered"]
            fc.status_code = archive_break_payload["status_code"]
            fc.final_verdict = Verdict.ok

        if not restart_loop:
            break


async def _phase_extract(fc: FetchContext, *, ctx: a2kit.ToolContext | None) -> None:
    """Run extraction on `body` (or use pre-rendered handler output)."""
    extract_dur_start = int((time.perf_counter() - fc.start_perf) * 1000)
    raw_html = fc.body.decode("utf-8", errors="replace") if fc.body else ""

    if fc.pre_rendered_payload is not None:
        # Site handler / archive / browser already produced markdown; skip trafilatura.
        fc.content_md = fc.pre_rendered_payload.content_md
        fc.title = fc.pre_rendered_payload.title
        fc.byline = fc.pre_rendered_payload.byline
        fc.headings = fc.pre_rendered_payload.headings
        return

    if not (fc.body and fc.final_verdict == Verdict.ok):
        return

    await _emit(ctx, StageStarted(t_ms=extract_dur_start, step="extract"))
    extract_result = await extract_markdown(raw_html, fc.final_url)
    fc.content_md = extract_result.content_md
    fc.title = extract_result.title
    fc.byline = extract_result.byline
    fc.published = extract_result.published
    fc.headings = extract_result.headings
    fc.links = extract_result.links
    fc.meta_dict = parse_metadata(raw_html)
    extract_dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - extract_dur_start
    fc.diagnostics.append(
        Diagnostic(
            t_ms=extract_dur_start,
            step="extract",
            engine="trafilatura",
            host=None,
            proxy=None,
            verdict=Verdict.ok,
            dur_ms=extract_dur_ms,
            extra={"chars": len(fc.content_md)},
        )
    )
    await _emit(
        ctx,
        StageEnded(
            t_ms=extract_dur_start,
            step="extract",
            verdict=Verdict.ok,
            dur_ms=extract_dur_ms,
            extra={"chars": len(fc.content_md)},
        ),
    )


async def _phase_gate_and_escalate(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext | None) -> None:
    """Run the gate; on signals, escalate to browser or archive (each capped to 1)."""
    if not (fc.body and fc.final_verdict == Verdict.ok):
        return

    gate_dur_start = int((time.perf_counter() - fc.start_perf) * 1000)
    await _emit(ctx, StageStarted(t_ms=gate_dur_start, step="gate"))

    # Pre-rendered handler results carry application/json bodies; skip the
    # html/content-type guard for them — block-page regexes still run on the
    # rendered markdown and length floor catches truly empty results.
    is_pre_rendered = fc.pre_rendered_payload is not None
    gate_content_type = None if is_pre_rendered else fc.content_type
    gate_raw_html = fc.content_md if is_pre_rendered else (fc.body.decode("utf-8", errors="replace") if fc.body else "")
    gate_result = evaluate(
        content_md=fc.content_md,
        raw_html=gate_raw_html,
        content_type=gate_content_type,
    )
    fc.gate_verdict = gate_result.verdict
    fc.gate_subsystem = gate_result.subsystem
    gate_dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - gate_dur_start
    fc.diagnostics.append(
        Diagnostic(
            t_ms=gate_dur_start,
            step="gate",
            engine="block_detector",
            host=None,
            proxy=None,
            verdict=fc.gate_verdict,
            subsystem=fc.gate_subsystem,
            dur_ms=gate_dur_ms,
            extra={},
        )
    )
    await _emit(
        ctx,
        StageEnded(t_ms=gate_dur_start, step="gate", verdict=fc.gate_verdict, dur_ms=gate_dur_ms),
    )
    if fc.gate_verdict != Verdict.ok:
        fc.final_verdict = fc.gate_verdict

    # Browser escalation — cap=1, only if gate flagged browser
    if gate_result.suggested_tier == "browser" and fc.browser_dispatches < 1 and fc.gate_verdict != Verdict.ok:
        await _escalate_browser(fc, state=state, ctx=ctx)

    # Archive escalation — cap=1 (shared with after-tier archive_dispatches)
    gate_action = next_action_after_gate(fc.gate_verdict, fc.final_url, state.settings)
    if isinstance(gate_action, RetryViaArchive) and fc.archive_dispatches < 1:
        fc.archive_dispatches += 1
        outcome = await _dispatch_archive(
            gate_action.url, state=state, ctx=ctx, start_perf=fc.start_perf, diagnostics=fc.diagnostics,
        )
        if outcome.success and outcome.pre_rendered is not None:
            fc.content_md = outcome.pre_rendered.content_md
            fc.title = outcome.pre_rendered.title
            fc.byline = outcome.pre_rendered.byline
            fc.headings = outcome.pre_rendered.headings
            fc.body = outcome.body
            fc.content_type = outcome.content_type
            fc.final_url = outcome.final_url
            fc.tier_used = "archive"
            fc.pre_rendered_payload = outcome.pre_rendered
            regate = evaluate(content_md=fc.content_md, raw_html=fc.content_md, content_type=None)
            if regate.verdict == Verdict.ok:
                fc.final_verdict = Verdict.ok
                fc.gate_verdict = Verdict.ok
            else:
                fc.final_verdict = regate.verdict
                fc.gate_verdict = regate.verdict
                fc.gate_subsystem = regate.subsystem


async def _escalate_browser(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext | None) -> None:
    """Dispatch the browser tier out-of-band; install its result on success."""
    browser_tier = REGISTRY["browser"]
    br_start_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    await _emit(ctx, TierStarted(t_ms=br_start_ms, step="browser", host=_host(fc.final_url)))
    browser_result = await browser_tier.fetch(fc.final_url, state=state)
    br_dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - br_start_ms
    fc.browser_dispatches += 1
    await _emit(
        ctx,
        TierEnded(
            t_ms=br_start_ms,
            step="browser",
            engine="camoufox",
            verdict=browser_result.verdict,
            dur_ms=br_dur_ms,
            extra={"status_code": browser_result.status_code},
        ),
    )
    fc.diagnostics.append(
        Diagnostic(
            t_ms=br_start_ms,
            step="browser",
            engine="camoufox",
            host=_host(fc.final_url),
            proxy=None,
            verdict=browser_result.verdict,
            dur_ms=br_dur_ms,
            extra={"status_code": browser_result.status_code},
        )
    )
    browser_pre = browser_result.pre_rendered
    if browser_result.verdict == Verdict.ok and browser_pre is not None:
        fc.content_md = browser_pre.content_md
        fc.title = browser_pre.title
        fc.byline = browser_pre.byline
        fc.headings = browser_pre.headings
        fc.body = browser_result.body
        fc.content_type = browser_result.content_type
        fc.final_url = browser_result.final_url
        fc.tier_used = "browser"
        fc.pre_rendered_payload = browser_pre
        fc.status_code = browser_result.status_code
        regate = evaluate(content_md=fc.content_md, raw_html=fc.content_md, content_type=None)
        if regate.verdict == Verdict.ok:
            fc.final_verdict = Verdict.ok
            fc.gate_verdict = Verdict.ok
            fc.gate_subsystem = None
        else:
            fc.final_verdict = regate.verdict
            fc.gate_verdict = regate.verdict
            fc.gate_subsystem = regate.subsystem
    else:
        fc.browser_unavailable_hint = browser_result.operator_hint


async def _phase_cache_write(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext | None) -> None:
    """Write to cache iff gate passed, non-hit, non-bypass, non-archive."""
    is_archive_result = fc.tier_used == "archive"
    should_cache = (
        fc.sqlite_conn is not None
        and not fc.bypass_cache
        and fc.cache_state != CacheState.hit
        and fc.final_verdict == Verdict.ok
        and fc.body
        and not is_archive_result
    )
    if not should_cache:
        return

    cache_dur_start = int((time.perf_counter() - fc.start_perf) * 1000)
    await _emit(ctx, StageStarted(t_ms=cache_dur_start, step="cache_write"))
    await cache_put(
        fc.sqlite_conn,
        fc.url,
        fc.profile_hash,
        etag=fc.etag,
        last_modified=fc.last_modified,
        status_code=fc.status_code,
        content_type=fc.content_type,
        body=fc.body,
        ttl_s=_ttl_for(fc.content_type, state.settings),
    )
    cache_dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - cache_dur_start
    await _emit(
        ctx,
        StageEnded(t_ms=cache_dur_start, step="cache_write", verdict=Verdict.ok, dur_ms=cache_dur_ms),
    )


# --------------------------------------------------------------------- #
# Top-level coordinator + response builder
# --------------------------------------------------------------------- #

async def _run_pipeline(
    fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext | None = None,
) -> FetchResponse:
    """Run the cascade end-to-end; return the response built from the context."""
    await _phase_cache_check(fc)
    await _phase_tier_loop(fc, state=state, ctx=ctx)
    # Cache hits still go through extract+gate — the body came from cache, but
    # the agent-facing fields (title, content_md, etc.) are produced by extraction.
    await _phase_extract(fc, ctx=ctx)
    await _phase_gate_and_escalate(fc, state=state, ctx=ctx)
    await _phase_cache_write(fc, state=state, ctx=ctx)
    return _build_response(fc)


def _build_response(fc: FetchContext) -> FetchResponse:
    """Materialize the FetchResponse from accumulated FetchContext state."""
    total_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    status = FetchStatus.ok if fc.final_verdict == Verdict.ok else FetchStatus.failed

    # fit_md preserved for response backward-compat — trafilatura's native
    # pruning produces output within 10% of v0.1 fit-md against every fixture.
    fit_md: str | None = fc.content_md if (fc.final_verdict == Verdict.ok and fc.content_md) else None

    narrative = _build_narrative(
        tier_used=fc.tier_used,
        cache_state=fc.cache_state,
        final_verdict=fc.final_verdict,
        total_ms=total_ms,
        gate_subsystem=fc.gate_subsystem,
    )

    tokens = (
        TokenCounts(full=len(fc.content_md), fit=len(fit_md or ""))
        if fc.final_verdict == Verdict.ok and fc.content_md
        else None
    )
    op_hints: list[OperatorHint] = []
    if fc.browser_unavailable_hint is not None:
        op_hints.append(fc.browser_unavailable_hint)

    return FetchResponse(
        url=fc.final_url,
        status=status,
        tier=fc.tier_used,
        confidence=_confidence_for(fc.final_verdict, fc.content_md),
        title=fc.title,
        byline=fc.byline,
        published=fc.published,
        started_at=fc.started_at,
        total_ms=total_ms,
        tokens=tokens,
        cache=fc.cache_state,
        narrative=narrative,
        diagnostics=fc.diagnostics,
        meta=fc.meta_dict,
        links=fc.links,
        headings=fc.headings,
        content_md=fc.content_md,
        fit_md=fit_md,
        operator_hints=op_hints,
    )


def _host(url: str) -> str | None:
    from urllib.parse import urlparse

    return urlparse(url).hostname


def _build_narrative(
    *,
    tier_used: str,
    cache_state: CacheState,
    final_verdict: Verdict,
    total_ms: int,
    gate_subsystem: str | None,
) -> str:
    if cache_state == CacheState.hit:
        return f"Cache hit ({fmt_dur(total_ms)})."
    if final_verdict == Verdict.ok:
        return f"{tier_used} → ok ({fmt_dur(total_ms)})."
    sub = f":{gate_subsystem}" if gate_subsystem else ""
    return f"{tier_used} → {final_verdict.value}{sub} ({fmt_dur(total_ms)})."
