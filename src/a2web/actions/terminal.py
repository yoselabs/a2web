"""Terminal classifier — the backward-looking sibling of the planner.

`playbook.decide_next(log) -> Action` chooses the NEXT escalation while the
cascade runs; `classify_terminal(log) -> TerminalOutcome` decides the terminal
STORY once it has stopped. Both are pure, total functions over the append-only
decision log — same substrate, same test style, no I/O.

This exists because the terminal story was previously split across two inverse
whitelist predicates (`_is_genuine_gone` / `_prescribe_browser_on_wall`) that
keyed on the *resolved verdict* — a projection. That could not see corroborating
evidence still in the log (two tiers independently observing HTTP 404 while a
mis-won thin tier set the resolved verdict to `length_floor`), so a dead URL was
dressed as an anti-bot wall. This classifier reads the OBSERVATIONS directly, so
that evidence is always reachable.

Imports nothing from `a2web.fetcher` — no I/O, no circular deps.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from ..decision_log import Observation, ObservationKind
from ..models import Verdict


class TerminalOutcome(StrEnum):
    """What a failed fetch MEANS to the caller. Closed set.

    - `wall`: a passable obstacle (content/transport/thin) — prescribe the
      caller's own browser (the ADR-0009 loud-miss floor).
    - `gone_confirmed`: the content is not there, and we are confident — a
      handler that models real "gone" semantics, OR an HTTP 404 corroborated by
      more than one independent tier. No browser prescription; a dead URL is not
      a wall.
    - `gone_unverified`: an HTTP 404 with no corroboration — most likely a dead
      URL, but the soft-404 check could not complete, so a small residual chance
      remains that a bot-defense is masking real content.
    - `operator_error`: a keyed paid tier failed auth/billing — a2web
      misconfiguration, not a site wall (carries its own dedicated hint).
    - `unreachable`: `dns_error` (domain does not resolve) or
      `content_type_mismatch` (a non-HTML resource WAS retrieved) — a browser
      cannot do better.
    """

    wall = "wall"
    gone_confirmed = "gone_confirmed"
    gone_unverified = "gone_unverified"
    operator_error = "operator_error"
    unreachable = "unreachable"


# Two independent tier observations of HTTP not_found corroborate "genuinely
# gone" — raw (direct) and jina (server-side) or the browser are distinct
# network paths, so agreement is evidence, not a single flaky read.
_CORROBORATION_THRESHOLD = 2

# Content-wall gate outcomes: when a gate ran and produced one of these, the page
# was retrieved and is walled/thin — a passable obstacle, not "gone". Any failing
# gate verdict that is not `not_found` is a wall for this purpose.
_WALL_GATE_VERDICTS = frozenset(
    {
        Verdict.block_page_detected,
        Verdict.anti_bot,
        Verdict.paywall,
        Verdict.blank_page,
        Verdict.length_floor,
        Verdict.other,
    }
)


def _last_gate_verdict(observations: Sequence[Observation]) -> Verdict | None:
    """The most recent gate-outcome verdict, or None if the gate never ran."""
    for obs in reversed(observations):
        if obs.kind is ObservationKind.gate_outcome:
            return obs.verdict
    return None


def classify_terminal(observations: Sequence[Observation], resolved_verdict: Verdict) -> TerminalOutcome:
    """Map the decision log of a FAILED fetch to a `TerminalOutcome`.

    Pure and total. Called only when the fetch did not end `ok`. Precedence:
    operator error → unreachable → authoritative gone → wall-gate → corroborated
    not-found (read from the observations so it survives a mis-won resolved
    verdict) → wall (the default passable-obstacle floor).
    """
    if resolved_verdict is Verdict.paid_auth_error:
        return TerminalOutcome.operator_error
    if resolved_verdict in (Verdict.dns_error, Verdict.content_type_mismatch):
        return TerminalOutcome.unreachable

    # An authoritative handler "gone" is definitive regardless of anything else.
    if any(o.authoritative and o.verdict is Verdict.not_found for o in observations):
        return TerminalOutcome.gone_confirmed

    # A definitive content-wall gate outcome (a retrieved-but-walled/thin page)
    # outranks a stray uncorroborated not_found — e.g. a handler's
    # escalate_to_render placeholder 404 co-occurring with a browser-rendered
    # block page. The page WAS reached and is walled; prescribe the browser.
    last_gate = _last_gate_verdict(observations)
    if last_gate in _WALL_GATE_VERDICTS:
        return TerminalOutcome.wall

    # not_found is keyed on what the cascade OBSERVED, not the projection: >=2
    # independent tiers seeing HTTP 404 is a confident miss; a single
    # uncorroborated 404 keeps the soft-404 caveat.
    not_found_obs = [o for o in observations if o.kind is ObservationKind.tier_outcome and o.verdict is Verdict.not_found]
    if len(not_found_obs) >= _CORROBORATION_THRESHOLD:
        return TerminalOutcome.gone_confirmed
    if not_found_obs:
        return TerminalOutcome.gone_unverified

    return TerminalOutcome.wall


__all__ = ["TerminalOutcome", "classify_terminal"]
