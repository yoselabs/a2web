"""The two promotions: a corroborated empty, and a corroborated complete small page."""

from __future__ import annotations

from ...actions.empty import is_complete_small_page, is_confirmed_empty
from ...hints import (
    content_empty_hint,
    has_hint,
)
from ...models import Verdict
from ..context import FetchContext

    # The never-silently-miss hint is emitted ONCE, systematically, by
    # `fetcher.verdict.terminal._apply_terminal` at the end of `_run_pipeline` —
    # not per-phase here. This phase only runs the gate + planner escalation
    # ladder.


def _has_browser_hint(fc: FetchContext) -> bool:
    return has_hint(fc.operator_hints, "try_user_browser")


def _has_hint(fc: FetchContext, code: str) -> bool:
    """Thin `FetchContext` adapter over `models.has_hint`.

    Was `any(h.code == code ...)` — an unvalidated twin of the shared helper,
    which is how a lookup for a renamed code would have gone on answering
    `False` here while the validated helper caught it everywhere else.
    """
    return has_hint(fc.operator_hints, code)


def _phase_empty_promotion(fc: FetchContext) -> None:
    """Promote a corroborated empty result to `ok` — BEFORE the failure classifier.

    `classify_terminal` is a failure taxonomy, so an `ok` empty is decided here,
    upstream, by the pure `is_confirmed_empty` conjunction. On promotion, set the
    `empty_confirmed` flag (the response builders read it to override status → ok
    and synthesize the "no results" answer) and attach the INFO `content_empty`
    hint. The verdict is deliberately left `length_floor` so `_phase_cache_write`
    still declines it — a wrongly-promoted empty must never be served from cache.
    Runs after every escalation phase so browser/subresource evidence is in the log.
    """
    if fc.resolved_verdict() is Verdict.ok:
        return
    if not is_confirmed_empty(fc.observations, fc.requested_url):
        return
    fc.empty_confirmed = True
    if not _has_hint(fc, "content_empty"):
        fc.operator_hints.append(content_empty_hint(fc.final_url))


def _phase_complete_small_page_promotion(fc: FetchContext) -> None:
    """Promote a corroborated COMPLETE small page to an extractable `ok`.

    The non-empty sibling of `_phase_empty_promotion` (empty-vs-wall-discrimination).
    Runs AFTER `_phase_gate_and_escalate` (so the corroborating browser render + its
    thin regate are in the log) and BEFORE `_phase_extract_answer` (so the flag can
    unlock extraction on the real body). Sets `small_page_confirmed` when the pure
    `is_complete_small_page` conjunction holds — a thin page whose independent browser
    render agreed it is small, with no wall evidence anywhere.

    The verdict is deliberately left `length_floor`: cache_write declines it (a
    wire-only promotion is never cached — design decision 1) and `_confidence_for`
    keeps it `low` (design decision 2). The final `ok` status is granted downstream
    by `small_page_promoted()` only when extraction produced a non-empty answer.
    """
    if fc.resolved_verdict() is Verdict.ok:
        return
    if not is_complete_small_page(fc.observations, fc.requested_url):
        return
    fc.small_page_confirmed = True
