"""The ordered phase chain, and nothing else.

This is the AGGREGATION POINT: its purpose IS to assemble. `_run_pipeline`
owns `_apply_terminal` rather than `_run_phases`, so ADR-0009's floor runs on
the `DeadlineExceeded` path too.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable

import aiosqlite

from .. import __version__
from .. import log as a2web_log
from ..decision_log import ObservationKind
from ..events import StageEnded
from ..feedback_transport import post_feedback_logs
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

_URL_REDACTED_PLACEHOLDER = "[url-redacted]"


def _redact_known_urls(text: str, urls: Iterable[str]) -> str:
    """Replace every occurrence of a known fetch URL in `text` with a placeholder.

    Unlike the gateway's collector-side regex scrub (which hunts for
    URL-*shaped* text and has already shipped two edge-case regressions —
    paren-eating, domain-truncation), this knows the EXACT URL strings the
    fetch itself used (`requested_url`/`url`/`final_url`) and does plain
    substring replacement — nothing to get wrong on a parenthesis or a
    bare-domain-without-scheme.
    """
    for url in urls:
        if url:
            text = text.replace(url, _URL_REDACTED_PLACEHOLDER)
    return text


async def _record_feedback(fc: FetchContext, state: AppState, *, response: FetchResponse) -> None:
    """Opt-in failure-feedback reporting (add-a2web-feedback-channel,
    unify-otel-telemetry-seam).

    Best-effort, mirrors `_record_uptake`: a fetch that resolved a warning/critical
    `OperatorHint` gets a condensed report POSTed to the configured gateway. No-op
    (no client built, no network touched) unless `feedback_enabled` is set — the
    default. Never raises: a dead gateway must never fail or delay the fetch it's
    reporting on.

    `OperatorHint`s are never emitted as log records (verified against every
    `fc.operator_hints.append(...)` call site) — this reads `fc.operator_hints`
    directly rather than attaching as a `logging.Handler`, since there is nothing
    on the `a2web` logger for a handler to observe.

    `feedback_include_content` is authoritative over every field capable of
    carrying a URL or query text, including `hint.message` — which embeds the
    failing URL by construction (see `hints.py`'s factories). Earlier this flag
    only gated a separate `url`/`query` attribute pair and left the message
    text always carrying the raw URL regardless of the flag (design.md D7 of
    `unify-otel-telemetry-seam`); redaction now happens here, at the one place
    that knows the exact URL strings involved, rather than relying solely on
    the gateway's best-effort regex scrub.

    `response` is the already-built `FetchResponse` — the SAME object the
    caller receives — so `result_status`/`result_confidence` are never a
    second, potentially-divergent computation of the outcome; they are
    exactly what a2web told its own caller (design.md D6 addendum:
    expectation-vs-result reporting).
    """
    settings = state.settings
    if not settings.feedback_enabled or not settings.feedback_api_key or not settings.feedback_endpoint:
        return
    reportable = [h for h in fc.operator_hints if h.severity in _REPORTABLE_SEVERITIES]
    if not reportable:
        return

    include_content = settings.feedback_include_content
    known_urls = (fc.inputs.requested_url, fc.url, fc.final_url)

    resource_attrs: list[dict[str, object]] = [
        {"key": "service.name", "value": {"stringValue": "a2web-feedback"}},
        {"key": "service.version", "value": {"stringValue": __version__}},
    ]
    operation = "query" if fc.inputs.ask is not None else "fetch_raw"
    expected = "an extracted answer from the requested URL" if operation == "query" else "raw page content from the requested URL"

    # Chain is one JSON-string attribute, not one attribute per step: the
    # gateway operator flagged that a nested `kvlistValue`'s storage-side
    # flattening is unverified against this specific OpenObserve build, and a
    # per-index attribute key (`chain.0`, `chain.1`, ...) risks one new column
    # per chain step per record against a stream whose schema is already a
    # per-record union with no fixed shape (design.md D5). A single string is
    # unambiguous either way.
    chain_steps = [
        {"source": obs.source, "verdict": str(obs.verdict), "authoritative": obs.authoritative, "t_ms": obs.t_ms} for obs in fc.observations
    ]
    chain_json = json.dumps(chain_steps)

    log_records = []
    for hint in reportable:
        attributes: list[dict[str, object]] = [
            {"key": "hint_code", "value": {"stringValue": hint.code}},
            # NOT "severity": the gateway stores OTLP `severityText` and a log
            # attribute of the same name in the same flat column, so a plain
            # "severity" attribute silently shadows severityText in storage
            # (confirmed live by the gateway operator). "feedback_severity"
            # keeps both distinguishable.
            {"key": "feedback_severity", "value": {"stringValue": hint.severity}},
            {"key": "operation", "value": {"stringValue": operation}},
            {"key": "expected", "value": {"stringValue": expected}},
            {"key": "result_status", "value": {"stringValue": str(response.status)}},
            {"key": "result_confidence", "value": {"stringValue": str(response.confidence)}},
            {"key": "status_code", "value": {"intValue": str(fc.status_code)}},
            {"key": "content_type", "value": {"stringValue": fc.content_type}},
            {"key": "cache_state", "value": {"stringValue": str(fc.cache_state)}},
            {"key": "tier_used", "value": {"stringValue": fc.tier_used}},
            {"key": "chain", "value": {"stringValue": chain_json}},
        ]
        if hint.fix:
            attributes.append({"key": "hint_fix", "value": {"stringValue": hint.fix}})
        body_text = hint.message if include_content else _redact_known_urls(hint.message, known_urls)
        if include_content:
            # `requested_url`/`final_url` — not `url` — are the authoritative
            # place to read the URL when content is enabled: the gateway's
            # attribute-redaction is name-anchored (`^url$`/`^query$`) and its
            # `body`-text scrub is unconditional regardless of this flag
            # (design.md D7 — the operator declined to relax it, correctly:
            # it is a boundary guarantee on a shared-key public endpoint, not
            # a stand-in for this flag). `body` may still show
            # `[url-redacted]` even with content included; these attributes
            # will not.
            attributes.append({"key": "requested_url", "value": {"stringValue": fc.inputs.requested_url}})
            attributes.append({"key": "final_url", "value": {"stringValue": fc.final_url or fc.url}})
            if fc.inputs.ask:
                # NOT "query": also name-anchored by the gateway's redaction
                # and would arrive as "****".
                attributes.append({"key": "requested_query", "value": {"stringValue": fc.inputs.ask}})
        log_records.append(
            {
                "timeUnixNano": str(time.time_ns()),
                "severityText": hint.severity.upper(),
                "body": {"stringValue": body_text},
                "attributes": attributes,
            }
        )

    await post_feedback_logs(settings, scope_name="a2web.feedback", resource_attrs=resource_attrs, log_records=log_records)
