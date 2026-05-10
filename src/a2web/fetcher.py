"""Fetch orchestrator — cache check → tier loop → extract → gate → cache write.

The orchestrator is the only place tier order is encoded. Tiers themselves
are pure-ish (HTTP I/O only); extraction is sync libraries via async
chokepoints; the gate is a pure function. Block pages NEVER enter the
cache (gate verdict gates the write).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import aiosqlite
import structlog

from .actions import RetryViaArchive, next_action_after_gate
from .cache.sqlite_cache import (
    cache_get,
    cache_put,
    compute_profile_hash,
    is_live_only,
)
from .events import EventBus, StageEnded, StageStarted, TierEnded, TierStarted
from .extract.htmldate_ext import find_published
from .extract.metadata import parse_metadata
from .extract.pruning_filter import prune_markdown
from .extract.trafilatura_ext import extract_markdown
from .gate.block_detector import evaluate
from .log.record import from_response as record_from_response
from .models import (
    CacheState,
    Confidence,
    Diagnostic,
    FetchResponse,
    FetchStatus,
    OperatorHint,
    TokenCounts,
    Verdict,
)
from .state import AppState, ensure_sqlite
from .tiers import REGISTRY, TIER_ORDER
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


async def fetch(url: str, *, state: AppState, bus: EventBus | None = None) -> FetchResponse:
    """Run the v0.1 cascade for one URL.

    `bus` is opt-in: when supplied, the orchestrator publishes phase
    boundary events (TierStarted/Ended, StageStarted/Ended) for live
    streaming. Without one, behavior matches PR5.
    """
    start_perf = time.perf_counter()
    started_at = datetime.now(UTC)
    diagnostics: list[Diagnostic] = []

    profile_hash = compute_profile_hash(state.settings)
    bypass_cache = is_live_only(url, state.settings)
    cache_state = CacheState.bypass if bypass_cache else CacheState.miss

    sqlite_conn = None if bypass_cache else await ensure_sqlite(state)
    response = await _run_pipeline(
        url=url,
        state=state,
        sqlite_conn=sqlite_conn,
        profile_hash=profile_hash,
        bypass_cache=bypass_cache,
        cache_state=cache_state,
        start_perf=start_perf,
        started_at=started_at,
        diagnostics=diagnostics,
        bus=bus,
    )

    if state.log_writer is not None:
        try:
            await state.log_writer.write_record(record_from_response(response, input_url=url))
        except Exception as exc:
            response.operator_hints.append(OperatorHint(code="log_write_failed", message=str(exc)))
            _LOG.warning("log_write_failed", error=str(exc), url=url)

    return response


async def _publish(bus: EventBus | None, event) -> None:
    if bus is not None:
        await bus.publish(event)


async def _run_pipeline(
    *,
    url: str,
    state: AppState,
    sqlite_conn: aiosqlite.Connection | None,
    profile_hash: str,
    bypass_cache: bool,
    cache_state: CacheState,
    start_perf: float,
    started_at: datetime,
    diagnostics: list[Diagnostic],
    bus: EventBus | None = None,
) -> FetchResponse:
    cached_row = None
    if sqlite_conn is not None:
        cached_row = await cache_get(sqlite_conn, url, profile_hash)

    body: bytes = b""
    final_url: str = url
    content_type: str = ""
    status_code: int = 0
    tier_used: str = "none"
    final_verdict: Verdict = Verdict.other
    etag: str | None = None
    last_modified: str | None = None
    pre_rendered_payload: dict | None = None

    # Phase 2 — tier loop (with conditional GET when cache row exists)
    for tier_name in TIER_ORDER:
        tier = REGISTRY[tier_name]
        tier_start_ms = int((time.perf_counter() - start_perf) * 1000)

        conditional_extras: dict[str, str] | None = None
        if cached_row is not None:
            conditional_extras = {}
            if cached_row.etag:
                conditional_extras["etag"] = cached_row.etag
            if cached_row.last_modified:
                conditional_extras["last_modified"] = cached_row.last_modified

        await _publish(bus, TierStarted(t_ms=tier_start_ms, step=tier_name, host=_host(url)))

        if isinstance(tier, RawTier):
            tier_result = await tier.fetch(url, state=state, conditional_extras=conditional_extras)
        else:
            tier_result = await tier.fetch(url, state=state)

        tier_dur_ms = int((time.perf_counter() - start_perf) * 1000) - tier_start_ms

        # site_handler "no match" / jina deny-list "skipped" — silent skip, no diagnostic row
        if tier_result.tier_extras.get("no_match") or tier_result.tier_extras.get("skipped"):
            continue

        await _publish(
            bus,
            TierEnded(
                t_ms=tier_start_ms,
                step=tier_result.tier_extras.get("handler_name") or tier_name,
                engine="curl_cffi" if tier_name == "raw" else None,
                verdict=tier_result.verdict,
                dur_ms=tier_dur_ms,
                extra={"status_code": tier_result.status_code},
            ),
        )

        # Conditional 304 → reuse cached body
        if tier_result.status_code == 304 and cached_row is not None and tier_result.tier_extras.get("conditional_hit"):
            body = cached_row.body
            content_type = cached_row.content_type or "text/html"
            status_code = 200  # logical hit
            cache_state = CacheState.hit
            etag = cached_row.etag
            last_modified = cached_row.last_modified
            final_url = url
            tier_used = tier_name
            final_verdict = Verdict.ok
            diagnostics.append(
                Diagnostic(
                    t_ms=tier_start_ms,
                    step=tier_name,
                    engine="curl_cffi",
                    host=_host(url),
                    proxy=None,
                    verdict=Verdict.ok,
                    dur_ms=tier_dur_ms,
                    extra={"conditional_hit": "true"},
                )
            )
            break

        diagnostics.append(
            Diagnostic(
                t_ms=tier_start_ms,
                step=tier_name,
                engine="curl_cffi" if tier_name == "raw" else None,
                host=_host(tier_result.final_url),
                proxy=None,
                verdict=tier_result.verdict,
                dur_ms=tier_dur_ms,
                extra={"status_code": tier_result.status_code},
            )
        )

        if tier_result.verdict == Verdict.ok:
            body = tier_result.body
            content_type = tier_result.content_type
            status_code = tier_result.status_code
            final_url = tier_result.final_url
            tier_used = tier_result.tier_extras.get("handler_name") or (tier.name if hasattr(tier, "name") else tier_name)
            final_verdict = Verdict.ok
            etag = tier_result.headers.get("etag")
            last_modified = tier_result.headers.get("last-modified")
            pre_rendered_payload = tier_result.tier_extras.get("pre_rendered")
            break

        # Tier failed; record verdict and (PR3) stop. Later PRs escalate.
        final_verdict = tier_result.verdict

    # Phase 3 — extraction (only when we have a body)
    extract_dur_start = int((time.perf_counter() - start_perf) * 1000)
    content_md = ""
    title = byline = None
    headings: list = []
    links: list = []
    meta_dict: dict[str, str] = {}
    published = None
    raw_html = body.decode("utf-8", errors="replace") if body else ""

    if pre_rendered_payload is not None:
        # Site handler already produced markdown; bypass trafilatura/htmldate/metadata.
        content_md = pre_rendered_payload.get("content_md", "")
        title = pre_rendered_payload.get("title")
        byline = pre_rendered_payload.get("byline")
        headings = pre_rendered_payload.get("headings", [])
        # links/meta intentionally empty for handler results in PR5; PR8 may revisit.
    elif body and final_verdict == Verdict.ok:
        await _publish(bus, StageStarted(t_ms=extract_dur_start, step="extract"))
        extract_result = await extract_markdown(raw_html, final_url)
        content_md = extract_result.content_md
        title = extract_result.title
        byline = extract_result.byline
        headings = extract_result.headings
        links = extract_result.links
        meta_dict = parse_metadata(raw_html)
        published = await find_published(raw_html, final_url)
        extract_dur_ms = int((time.perf_counter() - start_perf) * 1000) - extract_dur_start
        diagnostics.append(
            Diagnostic(
                t_ms=extract_dur_start,
                step="extract",
                engine="trafilatura",
                host=None,
                proxy=None,
                verdict=Verdict.ok,
                dur_ms=extract_dur_ms,
                extra={"chars": len(content_md)},
            )
        )
        await _publish(
            bus,
            StageEnded(
                t_ms=extract_dur_start,
                step="extract",
                verdict=Verdict.ok,
                dur_ms=extract_dur_ms,
                extra={"chars": len(content_md)},
            ),
        )

    # Phase 4 — gate
    gate_dur_start = int((time.perf_counter() - start_perf) * 1000)
    gate_verdict = Verdict.ok
    gate_subsystem: str | None = None
    if body and final_verdict == Verdict.ok:
        await _publish(bus, StageStarted(t_ms=gate_dur_start, step="gate"))
        # Pre-rendered handler results carry application/json bodies; skip the
        # html/content-type guard for them — block-page regexes still run on the
        # rendered markdown and length floor catches truly empty results.
        gate_content_type = None if pre_rendered_payload is not None else content_type
        gate_raw_html = content_md if pre_rendered_payload is not None else raw_html
        gate_result = evaluate(
            content_md=content_md,
            raw_html=gate_raw_html,
            content_type=gate_content_type,
        )
        gate_verdict = gate_result.verdict
        gate_subsystem = gate_result.subsystem
        gate_dur_ms = int((time.perf_counter() - start_perf) * 1000) - gate_dur_start
        diagnostics.append(
            Diagnostic(
                t_ms=gate_dur_start,
                step="gate",
                engine="block_detector",
                host=None,
                proxy=None,
                verdict=gate_verdict,
                subsystem=gate_subsystem,
                dur_ms=gate_dur_ms,
                extra={},
            )
        )
        await _publish(
            bus,
            StageEnded(t_ms=gate_dur_start, step="gate", verdict=gate_verdict, dur_ms=gate_dur_ms),
        )
        if gate_verdict != Verdict.ok:
            final_verdict = gate_verdict

        # Phase 4.25 — playbook escalation (paywall/block_page → archive)
        # Cap: 1 archive dispatch per fetch.
        gate_action = next_action_after_gate(gate_verdict, final_url, state.settings)
        if isinstance(gate_action, RetryViaArchive):
            archive_tier = REGISTRY["archive"]
            arch_start_ms = int((time.perf_counter() - start_perf) * 1000)
            await _publish(bus, TierStarted(t_ms=arch_start_ms, step="archive", host=_host(gate_action.url)))
            archive_result = await archive_tier.fetch(gate_action.url, state=state)
            arch_dur_ms = int((time.perf_counter() - start_perf) * 1000) - arch_start_ms
            await _publish(
                bus,
                TierEnded(
                    t_ms=arch_start_ms,
                    step="archive",
                    engine=str(archive_result.tier_extras.get("source", "archive")),
                    verdict=archive_result.verdict,
                    dur_ms=arch_dur_ms,
                    extra={"status_code": archive_result.status_code},
                ),
            )
            archive_pre = archive_result.tier_extras.get("pre_rendered")
            if archive_result.verdict == Verdict.ok and isinstance(archive_pre, dict):
                # Only record a diagnostic when archive recovers — a failed
                # escalation is "tried, didn't help" and should not displace
                # the original gate verdict in dominant-verdict logic.
                diagnostics.append(
                    Diagnostic(
                        t_ms=arch_start_ms,
                        step="archive",
                        engine=str(archive_result.tier_extras.get("source", "archive")),
                        host=_host(gate_action.url),
                        proxy=None,
                        verdict=archive_result.verdict,
                        dur_ms=arch_dur_ms,
                        extra={"status_code": archive_result.status_code},
                    )
                )
                # Replace state with archive's pre-rendered content; re-gate.
                content_md = archive_pre.get("content_md", "") or ""
                title = archive_pre.get("title")
                byline = archive_pre.get("byline")
                headings = archive_pre.get("headings", [])
                body = archive_result.body
                content_type = archive_result.content_type
                final_url = archive_result.final_url
                tier_used = "archive"
                pre_rendered_payload = archive_pre
                # Re-gate on archive content; no second escalation (cap=1).
                regate = evaluate(content_md=content_md, raw_html=content_md, content_type=None)
                if regate.verdict == Verdict.ok:
                    final_verdict = Verdict.ok
                    gate_verdict = Verdict.ok
                else:
                    final_verdict = regate.verdict
                    gate_verdict = regate.verdict
                    gate_subsystem = regate.subsystem

    # Phase 4.5 — fit_md (pruning filter for non-handler results)
    fit_md: str | None = None
    if final_verdict == Verdict.ok and content_md:
        if pre_rendered_payload is not None:
            # Handler results are already minimal; keep fit_md == content_md.
            fit_md = content_md
        else:
            fit_dur_start = int((time.perf_counter() - start_perf) * 1000)
            await _publish(bus, StageStarted(t_ms=fit_dur_start, step="fit"))
            try:
                pruned = await prune_markdown(raw_html, final_url)
            except Exception:
                pruned = ""
            fit_md = pruned if pruned else content_md
            fit_dur_ms = int((time.perf_counter() - start_perf) * 1000) - fit_dur_start
            await _publish(
                bus,
                StageEnded(
                    t_ms=fit_dur_start,
                    step="fit",
                    verdict=Verdict.ok,
                    dur_ms=fit_dur_ms,
                    extra={"chars": len(fit_md)},
                ),
            )

    # Phase 5 — cache write (gate-passed, non-hit only, non-bypass, non-archive)
    is_archive_result = tier_used == "archive"
    should_cache = (
        sqlite_conn is not None
        and not bypass_cache
        and cache_state != CacheState.hit
        and final_verdict == Verdict.ok
        and body
        and not is_archive_result
    )
    if should_cache:
        cache_dur_start = int((time.perf_counter() - start_perf) * 1000)
        await _publish(bus, StageStarted(t_ms=cache_dur_start, step="cache_write"))
        await cache_put(
            sqlite_conn,
            url,
            profile_hash,
            etag=etag,
            last_modified=last_modified,
            status_code=status_code,
            content_type=content_type,
            body=body,
            ttl_s=_ttl_for(content_type, state.settings),
        )
        cache_dur_ms = int((time.perf_counter() - start_perf) * 1000) - cache_dur_start
        await _publish(
            bus,
            StageEnded(t_ms=cache_dur_start, step="cache_write", verdict=Verdict.ok, dur_ms=cache_dur_ms),
        )

    total_ms = int((time.perf_counter() - start_perf) * 1000)
    status = FetchStatus.ok if final_verdict == Verdict.ok else FetchStatus.failed

    narrative = _build_narrative(
        tier_used=tier_used,
        cache_state=cache_state,
        final_verdict=final_verdict,
        total_ms=total_ms,
        gate_subsystem=gate_subsystem,
    )

    tokens = TokenCounts(full=len(content_md), fit=len(fit_md or "")) if final_verdict == Verdict.ok and content_md else None
    return FetchResponse(
        url=final_url,
        status=status,
        tier=tier_used,
        confidence=_confidence_for(final_verdict, content_md),
        title=title,
        byline=byline,
        published=published,
        started_at=started_at,
        total_ms=total_ms,
        tokens=tokens,
        cache=cache_state,
        narrative=narrative,
        diagnostics=diagnostics,
        meta=meta_dict,
        links=links,
        headings=headings,
        content_md=content_md,
        fit_md=fit_md,
        operator_hints=[],
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
