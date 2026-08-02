"""The gate, and the planner-driven escalation loop that follows it."""

from __future__ import annotations

import time
from urllib.parse import urlparse

from json_in_html import (
    is_json_content_type,
)

from .... import log as a2web_log
from ....actions import (
    EscalateBrowser,
    EscalatePaid,
    RetryViaArchive,
    decide_next,
)
from ....decision_log import ObservationKind
from ....events import StageEnded, StageStarted
from ....hints import (
    captcha_redirect_hint,
)
from ....models import Diagnostic, Verdict
from ....state import AppState
from ...comprehension.gate import evaluate
from ...context import FetchContext
from ...retrieval.escalate.paid import paid_budget_available
from ...retrieval.escalate.seam import Rung, escalate
from ...retrieval.tier_walk import _dispatch_action, _planner_caps


async def _phase_gate_and_escalate(fc: FetchContext, *, state: AppState) -> None:
    """Run the gate; on signals, escalate to browser or archive (each capped to 1)."""
    # Forced site render (escalate_to_render): a converting/walled handler asked
    # to render the original URL directly. Go STRAIGHT to the paid tier (Zyte
    # browserHtml) — the free ladder gets fooled by SPA shells / block pages, and
    # the own-browser is unreliable on them. On success the paid content installs
    # and is gated below like any other; if no paid tier is keyed, `_escalate_paid`
    # is a no-op and the empty body falls through to the never-silently-miss hint.
    if fc.render_requested and fc.pre_rendered_payload is None and paid_budget_available(fc):
        await escalate(fc, Rung.paid, state=state)
        # Paid tier absent/failed → try the own-browser BEFORE conceding. The
        # ladder is paid-scraper → real-browser → hint: a real (anti-detect)
        # browser passes soft per-IP walls the HTTP client cannot (e.g. Reddit
        # RSS throttling), and the local install ships Camoufox. A missing
        # backend short-circuits to an unavailable verdict (cheap no-op), so this
        # only installs content when a browser genuinely renders the surface.
        if fc.pre_rendered_payload is None and fc.browser_dispatches < 1:
            await escalate(fc, Rung.browser, state=state)
        # The render ladder was our only route (the free tiers were stopped). A
        # still-non-ok verdict here is a loud miss — but the never-silently-miss
        # hint is now emitted ONCE by `fetcher.verdict.terminal._apply_terminal`
        # at the end of `_run_pipeline` (the single systematic floor), not
        # per-phase here.

    if not (fc.body and fc.resolved_verdict() is Verdict.ok):
        return

    gate_dur_start = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2web_log.info(StageStarted(t_ms=gate_dur_start, step="gate"))

    # Pre-rendered handler results carry application/json bodies; skip the
    # html/content-type guard for them — block-page regexes still run on the
    # rendered markdown and length floor catches truly empty results.
    is_pre_rendered = fc.pre_rendered_payload is not None
    gate_content_type = None if is_pre_rendered else fc.content_type
    gate_raw_html = fc.content_md if is_pre_rendered else (fc.body.decode("utf-8", errors="replace") if fc.body else "")
    # A JSON response body is pre-rendered above, so `gate_content_type` is None;
    # thread the JSON-ness explicitly so the gate exempts a short JSON body from
    # the length floor (keyed on the original `fc.content_type`).
    gate_result = evaluate(
        content_md=fc.content_md,
        raw_html=gate_raw_html,
        content_type=gate_content_type,
        tier=fc.tier_used,
        host=urlparse(fc.final_url).hostname if fc.final_url else None,
        settings=state.settings,
        is_json=is_json_content_type(fc.content_type),
        structured_answer=any(c.answer_bearing for c in fc.content_candidates),
    )
    if gate_result.promoted_structured:
        fc.structured_grounded = True
    gate_dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - gate_dur_start
    fc.diagnostics.append(
        Diagnostic(
            t_ms=gate_dur_start,
            step="gate",
            engine="block_detector",
            host=None,
            proxy=None,
            verdict=gate_result.verdict,
            subsystem=gate_result.subsystem,
            dur_ms=gate_dur_ms,
            extra={},
        )
    )
    await a2web_log.info(
        StageEnded(t_ms=gate_dur_start, step="gate", verdict=gate_result.verdict, dur_ms=gate_dur_ms),
    )
    fc.observe(
        kind=ObservationKind.gate_outcome,
        source="gate",
        verdict=gate_result.verdict,
        escalation=gate_result.escalation,
        subsystem=gate_result.subsystem,
    )

    # v0.7: search-engine captcha escape — block detector flagged a Google/Bing
    # captcha page that slipped past `rewrite_captcha_host`. Surface an
    # actionable operator hint instead of just an opaque `block_page_detected`.
    if gate_result.subsystem == "captcha_redirect":
        fc.operator_hints.append(captcha_redirect_hint())

    # Planner-driven escalation. Consult `decide_next` over the decision log and
    # dispatch its action through the single unified executor, repeating until it
    # returns a non-escalation action. Each escalation is capped at one dispatch,
    # so the loop terminates. Only the three escalation actions are acted on here;
    # Continue (and the never-in-practice post-gate RewriteUrl) ends the loop —
    # matching the prior `else: break` exactly.
    while True:
        action = decide_next(fc.observations, url=fc.final_url, caps=_planner_caps(fc))
        if not isinstance(action, (EscalateBrowser, RetryViaArchive, EscalatePaid)):
            break
        await _dispatch_action(fc, action, state=state, post_gate=True)
