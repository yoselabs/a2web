"""The paid last-resort rung, and the shared one-dispatch budget."""

from __future__ import annotations

from ....actions import (
    PAID_DISPATCH_CAP,
)
from ....decision_log import ObservationKind
from ....hints import (
    paid_auth_error_hint,
)
from ....models import Diagnostic, Verdict
from ....state import AppState
from ....tiers import REGISTRY
from ...context import FetchContext, _within_budget
from ...retrieval.install import TierInstall, install
from ...telemetry import _emit_tier_ended, _emit_tier_started, _host
from ...verdict.promotions import _has_hint


def paid_budget_available(fc: FetchContext) -> bool:
    """One paid dispatch per fetch, claimed by four independent callers.

    The claimants, in the order they get to ask — which is the phase order, and
    therefore the precedence:

    1. `_phase_gate_and_escalate`'s forced site render (`render_requested`)
    2. the planner's `paid_last_resort` rule, post-gate
    3. `_obstacle_wants_render` — the extractor said the answer is not here
    4. `_listing_wants_render` — a partial listing worth scrolling

    **The precedence is real and is now stated rather than emergent.** It was
    four independent `paid_dispatches < 1` tests whose winner fell out of which
    phase happened to run first; reading the code told you the cap four times and
    the order zero times. This function does not CHANGE who wins — that would be
    a behaviour change, and this is a move — it makes the answer readable in one
    place. If the precedence should be different (an obstacle render arguably
    beats a listing scroll on value per dollar), that is its own change.
    """
    return fc.paid_dispatches < PAID_DISPATCH_CAP


# Paid tiers tried, in order, by `_escalate_paid`. Only names present in
# REGISTRY (i.e. keyed at boot) are actually dispatched; an un-keyed deployment
# has neither and the escalation is a single no-op that burns the paid budget so
# the planner falls through to the late never-silently-miss hint.
_PAID_TIER_ORDER = ("zyte", "firecrawl")


async def _escalate_paid(fc: FetchContext, *, state: AppState, scroll: bool = False) -> bool:
    """Dispatch the paid last-resort tier out-of-band; install on success.

    Returns whether content was installed; comprehension is `escalate`'s job.

    Cost-incurring, so capped at one escalation per fetch: `fc.paid_dispatches`
    is bumped unconditionally at entry (even when no paid tier is registered) so
    the planner's `paid_last_resort` rule cannot re-fire and spin.

    `scroll` (listing-completeness Slice 2) asks a browser-rendering paid tier
    to scroll the page before snapshotting — passed through to `tier.fetch`;
    tiers that don't render (Firecrawl) ignore it via `**kwargs`.

    FAIL-LOUD contract (task 4.6): a paid tier returning `paid_auth_error`
    (bad key / exhausted billing) records an AUTHORITATIVE observation and STOPS
    immediately — no fall-through to a sibling paid tier, no silent downgrade.
    The authoritative `paid_auth_error` (rank 12) then wins `resolve_verdict`, so
    the operator sees the real misconfiguration instead of a masked lower-tier
    result. A transient non-auth failure (timeout / connection) is recorded
    non-authoritatively and lets the next registered paid tier try.
    """
    fc.paid_dispatches += 1
    for tier_name in _PAID_TIER_ORDER:
        tier = REGISTRY.get(tier_name)
        if tier is None:
            continue  # un-keyed at boot — not registered.
        paid_start_ms = await _emit_tier_started(step=tier_name, host=_host(fc.final_url), start_perf=fc.start_perf)
        async with _within_budget(fc, about_to=f"tier:{tier.name}"):
            result = await tier.fetch(fc.final_url, state=state, scroll=scroll)
        paid_dur_ms = await _emit_tier_ended(
            step=tier_name,
            engine=tier_name,
            verdict=result.verdict,
            start_ms=paid_start_ms,
            start_perf=fc.start_perf,
            extra={"status_code": result.status_code},
        )
        fc.diagnostics.append(
            Diagnostic(
                t_ms=paid_start_ms,
                step=tier_name,
                engine=tier_name,
                host=_host(fc.final_url),
                proxy=None,
                verdict=result.verdict,
                dur_ms=paid_dur_ms,
                extra={"status_code": result.status_code},
            )
        )

        if result.verdict is Verdict.paid_auth_error:
            # Fail loud: authoritative hard-stop. Do NOT try the next paid tier.
            # The hint is the "loud" half — without it this returns `failed` +
            # `retrieval_incomplete` and nothing naming the fix, which is the
            # state three separate comments claimed was already handled here.
            if not _has_hint(fc, "paid_auth_error"):
                fc.operator_hints.append(paid_auth_error_hint(fc.final_url, tier=tier_name))
            fc.observe(
                kind=ObservationKind.tier_outcome,
                source=tier_name,
                verdict=Verdict.paid_auth_error,
                authoritative=True,
                status_code=result.status_code,
            )
            return False

        pre = result.pre_rendered
        if result.verdict is Verdict.ok and pre is not None:
            install(
                fc,
                TierInstall(
                    body=result.body,
                    content_type=result.content_type,
                    final_url=result.final_url,
                    tier_used=tier_name,
                    status_code=result.status_code,
                    pre_rendered=pre,
                    post_extract=True,
                ),
            )
            fc.observe(kind=ObservationKind.tier_outcome, source=tier_name, verdict=Verdict.ok)
            return True

        # Non-auth failure — record and let the next registered paid tier try.
        fc.observe(
            kind=ObservationKind.tier_outcome,
            source=tier_name,
            verdict=result.verdict,
            status_code=result.status_code,
        )
    return False
