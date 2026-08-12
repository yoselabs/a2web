"""The ordered phase chain, and nothing else.

This is the AGGREGATION POINT: its purpose IS to assemble. `_run_pipeline`
owns `_apply_terminal` rather than `_run_phases`, so ADR-0009's floor runs on
the `DeadlineExceeded` path too.
"""

from __future__ import annotations

import time

import aiosqlite
import httpx

from .. import __version__
from .. import log as a2web_log
from ..decision_log import ObservationKind
from ..events import StageEnded
from ..fetcher_response import build_response
from ..hints import (
    fetch_deadline_hint,
)
from ..log import log_warning
from ..models import FetchResponse, Verdict
from ..state import AppState
from ..uptake import note_visit, record_suggestions
from .answer.prompt_call import _phase_answer
from .comprehension.extract import _phase_extract
from .context import DeadlineExceeded, FetchContext
from .retrieval.cache import _phase_cache_check, _phase_cache_write
from .retrieval.cookies import _phase_cookies_staleness
from .retrieval.escalate.loop import _phase_gate_and_escalate
from .retrieval.tier_walk import _phase_tier_loop
from .verdict.promotions import _has_hint, _phase_complete_small_page_promotion, _phase_empty_promotion
from .verdict.terminal import _apply_terminal

# --------------------------------------------------------------------- #
# Top-level coordinator + response builder
# --------------------------------------------------------------------- #


async def _run_pipeline(
    fc: FetchContext,
    *,
    state: AppState,
) -> FetchResponse:
    """Run the cascade end-to-end; return the response built from the context."""
    try:
        await _run_phases(fc, state=state)
    except DeadlineExceeded as exc:
        # ADR-0009: a spent budget is an UNFINISHED JOB, never an outcome. Fall
        # through to the same terminal machinery every other failure uses, so
        # the caller gets `status: failed` + `retrieval_incomplete` + a loud
        # hint rather than a truncated success or an exception.
        await _record_deadline(fc, about_to=str(exc), state=state)
    _apply_terminal(fc)
    return build_response(fc)


async def _record_deadline(fc: FetchContext, *, about_to: str, state: AppState) -> None:
    """Log the expiry and attach the operator hint."""
    seconds = state.settings.fetch_deadline_s
    fc.observe(kind=ObservationKind.tier_outcome, source="deadline", verdict=Verdict.timeout)
    if not _has_hint(fc, "fetch_deadline_exceeded"):
        fc.operator_hints.append(fetch_deadline_hint(fc.final_url or fc.url, seconds=seconds, about_to=about_to))
    await a2web_log.warning(
        StageEnded(
            t_ms=int((time.perf_counter() - fc.inputs.start_perf) * 1000),
            step="deadline",
            verdict=Verdict.timeout,
            dur_ms=0,
            extra={"budget_s": f"{seconds:g}", "stopped_before": about_to},
        )
    )


async def _run_phases(
    fc: FetchContext,
    *,
    state: AppState,
) -> None:
    """The phase sequence. Any hop may raise `DeadlineExceeded`."""
    await _phase_cache_check(fc)
    await _phase_tier_loop(fc, state=state)
    # Cache hits still go through extract+gate — the body came from cache, but
    # the agent-facing fields (title, content_md, etc.) are produced by extraction.
    await _phase_extract(fc)
    await _phase_gate_and_escalate(fc, state=state)
    # empty-vs-wall-discrimination: a thin page whose independent browser render
    # agreed it is small (not walled) is promoted to an EXTRACTABLE ok — set the
    # flag here, AFTER the browser corroboration is in the log and BEFORE extraction,
    # so the extractor runs on the real body. Verdict stays length_floor (cache
    # declines it, confidence stays low); status → ok is granted downstream.
    _phase_complete_small_page_promotion(fc)
    # v0.4: optional LLM extraction. Runs only when ask= is set and the fetch
    # succeeded (or a complete-small-page was promoted). Graceful when no API key +
    # no Claude Code OAuth available.
    await _phase_answer(fc, state=state)
    await _phase_cache_write(fc, state=state)
    # empty-vs-wall-discrimination: promote a corroborated empty result to `ok`
    # BEFORE the failure floor. Runs after cache_write (which declines it — the
    # verdict stays length_floor) and before `_apply_terminal` (which stands down
    # on the `empty_confirmed` flag). A pure conjunction guards the promotion.
    _phase_empty_promotion(fc)
    # v0.8: emit cookies_stale hint once per fetch when mirror is stale.
    await _phase_cookies_staleness(fc, state=state)


async def _record_uptake(fc: FetchContext, state: AppState) -> None:
    """Best-effort suggestion-uptake telemetry (D12 / task 8.2).

    Two correlated writes on the shared sqlite connection: (1) `note_visit` marks
    any earlier suggestion of THIS ask's requested url as followed — a non-zero
    return means the caller acted on a prior `other_pages` pointer; (2) `record_suggestions`
    logs the (rehydrated) targets this ask now emits, for a future ask to close.
    Uses `requested_url` (the caller's actual input, pre-rewrite) as the join key.

    Telemetry must never fail a fetch — a sqlite hiccup is swallowed to a warning.
    """
    try:
        conn = await state.sqlite.ensure()
        followed = await note_visit(conn, fc.inputs.requested_url)
        if followed:
            await a2web_log.info("other_pages_followed", url=fc.inputs.requested_url, fulfilled=followed)
        targets = [(e.url, e.off_domain) for e in (fc.routing.other_pages if fc.routing else ()) if e.url]
        stored = await record_suggestions(conn, source_url=fc.inputs.requested_url, question=fc.inputs.ask, targets=targets)
        if stored:
            await a2web_log.info("other_pages_suggested", url=fc.inputs.requested_url, count=stored)
    except (aiosqlite.Error, OSError) as exc:  # telemetry is best-effort — never break the fetch
        log_warning("uptake_write_failed", error=str(exc))


#: Hint severities that qualify for a feedback report. `info` hints are routine
#: (e.g. an authoritative empty result) — reporting those would flood the
#: gateway with noise carrying no operator value.
_REPORTABLE_SEVERITIES = frozenset({"warning", "critical"})


async def _record_feedback(fc: FetchContext, state: AppState) -> None:
    """Opt-in failure-feedback reporting (add-a2web-feedback-channel).

    Best-effort, mirrors `_record_uptake`: a fetch that resolved a warning/critical
    `OperatorHint` gets a condensed report POSTed to the configured gateway. No-op
    (no client built, no network touched) unless `feedback_enabled` is set — the
    default. Never raises: a dead gateway must never fail or delay the fetch it's
    reporting on.

    `OperatorHint`s are never emitted as log records (verified against every
    `fc.operator_hints.append(...)` call site) — this reads `fc.operator_hints`
    directly rather than attaching as a `logging.Handler`, since there is nothing
    on the `a2web` logger for a handler to observe.
    """
    settings = state.settings
    if not settings.feedback_enabled or not settings.feedback_api_key or not settings.feedback_endpoint:
        return
    reportable = [h for h in fc.operator_hints if h.severity in _REPORTABLE_SEVERITIES]
    if not reportable:
        return

    last_observation = fc.observations[-1] if fc.observations else None
    resource_attrs: list[dict[str, object]] = [
        {"key": "service.name", "value": {"stringValue": "a2web-feedback"}},
        {"key": "service.version", "value": {"stringValue": __version__}},
    ]
    log_records = []
    for hint in reportable:
        attributes: list[dict[str, object]] = [
            {"key": "hint_code", "value": {"stringValue": hint.code}},
            {"key": "severity", "value": {"stringValue": hint.severity}},
        ]
        if last_observation is not None:
            attributes.append({"key": "tier", "value": {"stringValue": last_observation.source}})
            attributes.append({"key": "verdict", "value": {"stringValue": str(last_observation.verdict)}})
        if settings.feedback_include_content:
            attributes.append({"key": "url", "value": {"stringValue": fc.final_url or fc.url}})
            if fc.inputs.ask:
                attributes.append({"key": "query", "value": {"stringValue": fc.inputs.ask}})
        log_records.append(
            {
                "timeUnixNano": str(time.time_ns()),
                "severityText": hint.severity.upper(),
                "body": {"stringValue": hint.message},
                "attributes": attributes,
            }
        )

    payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": resource_attrs},
                "scopeLogs": [{"scope": {"name": "a2web.feedback"}, "logRecords": log_records}],
            }
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                settings.feedback_endpoint,
                json=payload,
                headers={"X-Api-Key": settings.feedback_api_key},
            )
    except (httpx.HTTPError, OSError) as exc:  # telemetry is best-effort — never break the fetch
        log_warning("feedback_report_failed", error=str(exc))
