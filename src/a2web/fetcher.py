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
from enum import Enum

import a2kit
import a2kit.ldd
import structlog

from .actions import RetryViaArchive, RewriteUrl, next_action_after_gate, next_action_after_tier
from .cache.sqlite_cache import (
    CacheRow,
    SqliteResource,
    compute_profile_hash,
    is_live_only,
)
from .events import StageEnded, StageStarted, TierEnded, TierStarted
from .extract.metadata import parse_metadata
from .extract.trafilatura_ext import extract_markdown
from .gate.block_detector import evaluate
from .models import (
    CacheState,
    Confidence,
    Diagnostic,
    ExtractionMeta,
    FetchResponse,
    FetchStatus,
    Heading,
    Link,
    OperatorHint,
    TokenCounts,
    Verdict,
)
from .state import AppState
from .tiers import REGISTRY, TIER_ORDER, Rendered, Tier, TierResult
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
    sqlite: SqliteResource | None
    bypass_cache: bool

    # URL state (rewritten on after-tier RewriteUrl)
    url: str
    final_url: str

    # Response-shape opt-ins (v0.3 envelope diet)
    include_links: bool = False
    debug: bool = False
    # v0.4: optional LLM extraction question + outputs
    ask: str | None = None
    extracted_answer: str | None = None
    extraction_meta: ExtractionMeta | None = None

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

    # Diagnostics + operator-hint accumulators — anywhere in the pipeline can append.
    diagnostics: list[Diagnostic] = field(default_factory=list)
    operator_hints: list[OperatorHint] = field(default_factory=list)


async def fetch(
    url: str,
    *,
    state: AppState,
    ctx: a2kit.ToolContext | None = None,
    include_links: bool = False,
    debug: bool = False,
    ask: str | None = None,
) -> FetchResponse:
    """Run the v0.1 cascade for one URL.

    `ctx` is the a2kit ToolContext. The orchestrator emits typed phase-boundary
    events via `await a2kit.ldd.event(ctx, EventInstance(...))`. When the caller
    passes None (eval/systems direct call, unit tests bypassing the dispatcher),
    the entry point swaps in `a2kit.testing.null_context()` so internal phase
    functions receive a non-Optional ctx and stay guard-free.

    `include_links` and `debug` are v0.3 envelope-diet opt-ins (both default
    False). See `FetchResponse` docs.

    `ask` (v0.4) opts into server-side LLM extraction: when set, an LLM
    reads `content_md` and produces an answer string returned on
    `extracted_answer`. Graceful when the `[llm]` extra is missing or the
    API key is unset — `extracted_answer` stays None and an operator hint
    is recorded.
    """
    start_perf = time.perf_counter()
    started_at = datetime.now(UTC)

    if ctx is None:
        from a2kit.testing import null_context

        ctx = null_context()

    profile_hash = compute_profile_hash(state.settings)
    bypass_cache = is_live_only(url, state.settings)
    sqlite = None if bypass_cache else state.sqlite

    fc = FetchContext(
        started_at=started_at,
        start_perf=start_perf,
        profile_hash=profile_hash,
        sqlite=sqlite,
        bypass_cache=bypass_cache,
        url=url,
        final_url=url,
        include_links=include_links,
        debug=debug,
        ask=ask,
        cache_state=CacheState.bypass if bypass_cache else CacheState.miss,
    )

    response = await _run_pipeline(fc, state=state, ctx=ctx)

    if state.log_writer is not None:
        try:
            await state.log_writer.write_record(response.to_log_record(input_url=url))
        except Exception as exc:
            response.operator_hints.append(OperatorHint(code="log_write_failed", message=str(exc)))
            _LOG.warning("log_write_failed", error=str(exc), url=url)

    # v0.3 envelope diet: apply opt-in gates AT THE WIRE BOUNDARY. Logging
    # has already consumed the full diagnostics; agents see the slim version.
    # `diagnostics_summary` is always populated and carries verdict + timing.
    if not fc.include_links:
        response.links = []
    if not fc.debug:
        response.diagnostics = []

    return response


# --------------------------------------------------------------------- #
# Event emission helpers
# --------------------------------------------------------------------- #


# Note: typed events emit directly via `await a2kit.ldd.event(ctx, event)`.
# Round-4: a2kit's free function now honors registered dataclass instances and
# serializes them via `dataclasses.asdict` + Enum.value coercion. No flattener
# needed at this seam.


# --------------------------------------------------------------------- #
# Tier emission helpers — shared by tier loop + escalators
# --------------------------------------------------------------------- #


async def _emit_tier_started(
    ctx: a2kit.ToolContext,
    *,
    step: str,
    host: str | None,
    start_perf: float,
) -> int:
    """Emit `TierStarted` at the current perf-clock tick; return the relative ms."""
    start_ms = int((time.perf_counter() - start_perf) * 1000)
    await a2kit.ldd.event(ctx, TierStarted(t_ms=start_ms, step=step, host=host))
    return start_ms


async def _emit_tier_ended(
    ctx: a2kit.ToolContext,
    *,
    step: str,
    engine: str | None,
    verdict: Verdict,
    start_ms: int,
    start_perf: float,
    extra: dict[str, str | int] | None = None,
) -> int:
    """Emit `TierEnded` and return the elapsed `dur_ms` (relative to `start_ms`)."""
    dur_ms = int((time.perf_counter() - start_perf) * 1000) - start_ms
    await a2kit.ldd.event(
        ctx,
        TierEnded(
            t_ms=start_ms,
            step=step,
            engine=engine,
            verdict=verdict,
            dur_ms=dur_ms,
            extra=extra or {},
        ),
    )
    return dur_ms


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
    ctx: a2kit.ToolContext,
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
    arch_start_ms = await _emit_tier_started(ctx, step="archive", host=_host(url), start_perf=start_perf)
    archive_result = await archive_tier.fetch(url, state=state)
    engine = archive_result.archive_source or "archive"
    arch_dur_ms = await _emit_tier_ended(
        ctx,
        step="archive",
        engine=engine,
        verdict=archive_result.verdict,
        start_ms=arch_start_ms,
        start_perf=start_perf,
        extra={"status_code": archive_result.status_code},
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
    if fc.sqlite is not None:
        fc.cached_row = await fc.sqlite.get(fc.url, fc.profile_hash)


class _AfterTier(Enum):
    """Outcome of `_apply_after_tier_action` — drives outer-loop control flow."""

    NONE = "none"  # no rewrite / archive — continue normal tier-loop flow
    REWRITE = "rewrite"  # URL was rewritten — restart the loop
    ARCHIVE_INSTALLED = "archive_installed"  # archive content installed onto fc


def _install_won_tier(
    fc: FetchContext,
    tier_result: TierResult,
    tier_name: str,
    tier: Tier,
) -> None:
    """Install a winning (`Verdict.ok`) tier result onto FetchContext."""
    fc.body = tier_result.body
    fc.content_type = tier_result.content_type
    fc.status_code = tier_result.status_code
    fc.final_url = tier_result.final_url
    fc.tier_used = tier_result.handler_name or (tier.name if hasattr(tier, "name") else tier_name)
    fc.final_verdict = Verdict.ok
    fc.etag = tier_result.headers.get("etag")
    fc.last_modified = tier_result.headers.get("last-modified")
    fc.pre_rendered_payload = tier_result.pre_rendered


def _install_archive_payload(fc: FetchContext, outcome: _ArchiveOutcome) -> None:
    """Install a successful archive escalation outcome onto FetchContext."""
    fc.body = outcome.body
    fc.content_type = outcome.content_type
    fc.final_url = outcome.final_url
    fc.tier_used = "archive"
    fc.pre_rendered_payload = outcome.pre_rendered
    fc.status_code = outcome.status_code
    fc.final_verdict = Verdict.ok


async def _apply_after_tier_action(
    fc: FetchContext,
    tier_result: TierResult,
    *,
    state: AppState,
    ctx: a2kit.ToolContext,
) -> _AfterTier:
    """Run the after-tier action (URL rewrite, archive retry) and report outcome.

    Caps: `RewriteUrl` and `RetryViaArchive` each fire at most once per
    fetch. On `REWRITE`, the new URL is installed on `fc` and the
    cached row is reloaded. On `ARCHIVE_INSTALLED`, the archive payload
    is installed on `fc` (caller can return from the tier loop).
    """
    tier_action = next_action_after_tier(tier_result, fc.url)

    if isinstance(tier_action, RewriteUrl) and fc.url_rewrites < 1:
        fc.url_rewrites += 1
        fc.url = tier_action.new_url
        fc.final_url = fc.url
        # Reset cached_row — new URL likely has its own cache entry.
        if fc.sqlite is not None:
            fc.cached_row = await fc.sqlite.get(fc.url, fc.profile_hash)
        else:
            fc.cached_row = None
        return _AfterTier.REWRITE

    if isinstance(tier_action, RetryViaArchive) and fc.archive_dispatches < 1:
        fc.archive_dispatches += 1
        outcome = await _dispatch_archive(
            tier_action.url,
            state=state,
            ctx=ctx,
            start_perf=fc.start_perf,
            diagnostics=fc.diagnostics,
        )
        if outcome.success:
            _install_archive_payload(fc, outcome)
            return _AfterTier.ARCHIVE_INSTALLED
        # Archive failed — keep trying tiers (fall through).

    return _AfterTier.NONE


async def _phase_tier_loop(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext) -> None:
    """Walk TIER_ORDER, dispatch each tier, run after-tier actions, until one wins or all fail.

    Supports two interruptions of the linear flow:
    - `RewriteUrl` from after-tier action → restart the loop with the new URL (cap=1).
    - `RetryViaArchive` from after-tier action → out-of-band archive dispatch (cap=1).
    """
    proxy_pool = state.proxy_pool

    while True:
        restart_loop = False
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

            await a2kit.ldd.event(ctx, TierStarted(t_ms=tier_start_ms, step=tier_name, host=_host(fc.url)))

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

            # Silent skip — no diagnostic row
            if tier_result.no_match or tier_result.skipped:
                continue

            proxy_pool.report(
                handle,
                success=tier_result.verdict not in (Verdict.proxy_unavailable, Verdict.connection_error, Verdict.timeout),
            )

            tier_dur_ms = await _emit_tier_ended(
                ctx,
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

            after = await _apply_after_tier_action(fc, tier_result, state=state, ctx=ctx)
            if after is _AfterTier.REWRITE:
                restart_loop = True
                break  # break inner for; while True restarts
            if after is _AfterTier.ARCHIVE_INSTALLED:
                return

            if tier_result.verdict == Verdict.ok:
                _install_won_tier(fc, tier_result, tier_name, tier)
                return

            fc.final_verdict = tier_result.verdict

        if not restart_loop:
            return


async def _phase_extract(fc: FetchContext, *, ctx: a2kit.ToolContext) -> None:
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

    await a2kit.ldd.event(ctx, StageStarted(t_ms=extract_dur_start, step="extract"))
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
    await a2kit.ldd.event(
        ctx,
        StageEnded(
            t_ms=extract_dur_start,
            step="extract",
            verdict=Verdict.ok,
            dur_ms=extract_dur_ms,
            extra={"chars": len(fc.content_md)},
        ),
    )


async def _phase_gate_and_escalate(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext) -> None:
    """Run the gate; on signals, escalate to browser or archive (each capped to 1)."""
    if not (fc.body and fc.final_verdict == Verdict.ok):
        return

    gate_dur_start = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.ldd.event(ctx, StageStarted(t_ms=gate_dur_start, step="gate"))

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
    await a2kit.ldd.event(
        ctx,
        StageEnded(t_ms=gate_dur_start, step="gate", verdict=fc.gate_verdict, dur_ms=gate_dur_ms),
    )
    if fc.gate_verdict != Verdict.ok:
        fc.final_verdict = fc.gate_verdict

    # Browser escalation — cap=1, only if gate flagged browser
    if gate_result.suggested_tier == "browser" and fc.browser_dispatches < 1 and fc.gate_verdict != Verdict.ok:
        await _escalate_browser(fc, state=state, ctx=ctx)

    # Archive escalation — cap=1 (shared with after-tier archive_dispatches)
    gate_action = next_action_after_gate(fc.gate_verdict, fc.final_url)
    if isinstance(gate_action, RetryViaArchive) and fc.archive_dispatches < 1:
        fc.archive_dispatches += 1
        outcome = await _dispatch_archive(
            gate_action.url,
            state=state,
            ctx=ctx,
            start_perf=fc.start_perf,
            diagnostics=fc.diagnostics,
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


async def _escalate_browser(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext) -> None:
    """Dispatch the browser tier out-of-band; install its result on success."""
    browser_tier = REGISTRY["browser"]
    br_start_ms = await _emit_tier_started(
        ctx, step="browser", host=_host(fc.final_url), start_perf=fc.start_perf
    )
    browser_result = await browser_tier.fetch(fc.final_url, state=state)
    fc.browser_dispatches += 1
    br_dur_ms = await _emit_tier_ended(
        ctx,
        step="browser",
        engine="camoufox",
        verdict=browser_result.verdict,
        start_ms=br_start_ms,
        start_perf=fc.start_perf,
        extra={"status_code": browser_result.status_code},
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
    elif browser_result.operator_hint is not None:
        fc.operator_hints.append(browser_result.operator_hint)


async def _phase_cache_write(fc: FetchContext, *, state: AppState, ctx: a2kit.ToolContext) -> None:
    """Write to cache iff gate passed, non-hit, non-bypass, non-archive."""
    is_archive_result = fc.tier_used == "archive"
    should_cache = (
        fc.sqlite is not None
        and not fc.bypass_cache
        and fc.cache_state != CacheState.hit
        and fc.final_verdict == Verdict.ok
        and fc.body
        and not is_archive_result
    )
    if not should_cache:
        return
    assert fc.sqlite is not None  # noqa: S101 — narrowed by should_cache

    cache_dur_start = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.ldd.event(ctx, StageStarted(t_ms=cache_dur_start, step="cache_write"))
    await fc.sqlite.put(
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
    await a2kit.ldd.event(
        ctx,
        StageEnded(t_ms=cache_dur_start, step="cache_write", verdict=Verdict.ok, dur_ms=cache_dur_ms),
    )


# --------------------------------------------------------------------- #
# Top-level coordinator + response builder
# --------------------------------------------------------------------- #


async def _run_pipeline(
    fc: FetchContext,
    *,
    state: AppState,
    ctx: a2kit.ToolContext,
) -> FetchResponse:
    """Run the cascade end-to-end; return the response built from the context."""
    await _phase_cache_check(fc)
    await _phase_tier_loop(fc, state=state, ctx=ctx)
    # Cache hits still go through extract+gate — the body came from cache, but
    # the agent-facing fields (title, content_md, etc.) are produced by extraction.
    await _phase_extract(fc, ctx=ctx)
    await _phase_gate_and_escalate(fc, state=state, ctx=ctx)
    await _phase_cache_write(fc, state=state, ctx=ctx)
    # v0.4: optional LLM extraction. Runs only when ask= is set and the fetch
    # succeeded. Graceful when the [llm] extra or API key is unavailable.
    await _phase_extract_answer(fc, state=state, ctx=ctx)
    return _build_response(fc)


async def _phase_extract_answer(
    fc: FetchContext,
    *,
    state: AppState,
    ctx: a2kit.ToolContext,
) -> None:
    """Run server-side LLM extraction when ask= is set. v0.4."""
    if fc.ask is None:
        return
    if fc.final_verdict != Verdict.ok or not fc.content_md:
        # Failed fetches don't get extraction — no content to extract from.
        # The agent will see status=failed + diagnostics_summary explaining why.
        return

    phase_start_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.ldd.event(ctx, StageStarted(t_ms=phase_start_ms, step="extract_answer"))

    result = await state.llm_extractor.extract(content=fc.content_md, ask=fc.ask)
    if result is None:
        # Graceful degrade: fetch succeeded, extraction skipped, operator
        # hint surfaces the actionable reason.
        reason = state.llm_extractor.unavailable_reason or "LLM extractor unavailable"
        fc.operator_hints.append(
            OperatorHint(
                code="llm_unavailable",
                message=reason,
                fix=f"Install with `pip install a2web[llm]` and set {state.settings.llm_api_key_env} in the environment.",
            )
        )
        dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - phase_start_ms
        await a2kit.ldd.event(
            ctx,
            StageEnded(
                t_ms=phase_start_ms,
                step="extract_answer",
                verdict=Verdict.other,
                dur_ms=dur_ms,
                extra={"skipped": "llm_unavailable"},
            ),
        )
        return
    fc.extracted_answer = result.answer
    fc.extraction_meta = ExtractionMeta(
        model=result.model,
        template_name=result.template_name,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        cache_hit=result.cache_hit,
        truncated=bool(result.raw and result.raw.get("truncated")),
    )
    dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - phase_start_ms
    await a2kit.ldd.event(
        ctx,
        StageEnded(
            t_ms=phase_start_ms,
            step="extract_answer",
            verdict=Verdict.ok,
            dur_ms=dur_ms,
            extra={
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            },
        ),
    )


def _build_response(fc: FetchContext) -> FetchResponse:
    """Materialize the FetchResponse from accumulated FetchContext state."""
    total_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    status = FetchStatus.ok if fc.final_verdict == Verdict.ok else FetchStatus.failed

    # v0.3: fit_md is None until a real pruning filter ships. The field stays
    # on the model for forward-compat; we stopped populating it as a duplicate
    # of content_md (saved ~19% of total payload across the benchmark corpus).
    fit_md: str | None = None

    narrative = _build_narrative(
        tier_used=fc.tier_used,
        cache_state=fc.cache_state,
        final_verdict=fc.final_verdict,
        total_ms=total_ms,
        gate_subsystem=fc.gate_subsystem,
    )

    tokens = TokenCounts(full=len(fc.content_md), fit=len(fit_md or "")) if fc.final_verdict == Verdict.ok and fc.content_md else None
    op_hints: list[OperatorHint] = list(fc.operator_hints)

    diagnostics_summary = _build_diagnostics_summary(
        tier_used=fc.tier_used,
        final_verdict=fc.final_verdict,
        total_ms=total_ms,
        gate_subsystem=fc.gate_subsystem,
    )

    # v0.3 envelope diet is applied at the wire boundary in `fetch()` AFTER
    # the log writer reads the response — so this builder always emits the
    # full diagnostics + links. Callers wanting the diet effect must invoke
    # via `fetch()`, not `_build_response()` directly.
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
        diagnostics_summary=diagnostics_summary,
        diagnostics=fc.diagnostics,
        meta=fc.meta_dict,
        links=fc.links,
        headings=fc.headings,
        content_md=fc.content_md,
        fit_md=fit_md,
        operator_hints=op_hints,
        extracted_answer=fc.extracted_answer,
        extraction=fc.extraction_meta,
    )


def _build_diagnostics_summary(
    *,
    tier_used: str,
    final_verdict: Verdict,
    total_ms: int,
    gate_subsystem: str | None,
) -> str:
    """One-line summary of the fetch outcome. Always populated.

    Shape: `tier=<x> verdict=<v> total_ms=<n>[ extras=<failure_code>]`.
    """
    parts = [
        f"tier={tier_used}",
        f"verdict={final_verdict.value}",
        f"total_ms={total_ms}",
    ]
    if final_verdict != Verdict.ok and gate_subsystem:
        parts.append(f"extras={gate_subsystem}")
    return " ".join(parts)


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
