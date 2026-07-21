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

    - `wall`: a passable obstacle (content/transport) — prescribe the
      caller's own browser (the ADR-0009 loud-miss floor).
    - `gone_confirmed`: the content is not there, and we are confident — a
      handler that models real "gone" semantics, OR an HTTP 404 corroborated by
      more than one independent tier. No browser prescription; a dead URL is not
      a wall.
    - `gone_unverified`: an HTTP 404 with no corroboration — most likely a dead
      URL, but the soft-404 check could not complete, so a small residual chance
      remains that a bot-defense is masking real content.
    - `thin_unverified`: a retrieved HTTP 200 that rendered thin (`length_floor`)
      with NO hard-wall evidence AND no empty-result marker anywhere in the log —
      genuinely AMBIGUOUS between an empty result set / minimal page and a bespoke
      or IP-reputation wall a2web could not fingerprint. By this terminal the
      planner has already escalated the thin body to a real browser (fast +
      robust) and it stayed thin, so the "needs a browser" hypothesis was tested,
      not assumed — but the empty-vs-wall discriminator is not reliably in the
      body text, so a2web asserts neither. Honest WARNING (worded agnostically)
      with the retrieved body attached; NOT the CRITICAL wall klaxon.
    - `empty_unverified`: like `thin_unverified` but an empty-result marker DID
      match (`subsystem="empty_result"`) — leans empty, yet the promotion
      conjunction (`is_confirmed_empty`) did not hold, so it stays a WARNING with
      the body attached, never promoted to `ok` on the marker alone.
    - `operator_error`: a keyed paid tier failed auth/billing — a2web
      misconfiguration, not a site wall (carries its own dedicated hint).
    - `unreachable`: `dns_error` (domain does not resolve) or
      `content_type_mismatch` (a non-HTML resource WAS retrieved) — a browser
      cannot do better.
    """

    wall = "wall"
    gone_confirmed = "gone_confirmed"
    gone_unverified = "gone_unverified"
    thin_unverified = "thin_unverified"
    empty_unverified = "empty_unverified"
    operator_error = "operator_error"
    unreachable = "unreachable"


# Two independent tier observations of HTTP not_found corroborate "genuinely
# gone" — raw (direct) and jina (server-side) or the browser are distinct
# network paths, so agreement is evidence, not a single flaky read.
_CORROBORATION_THRESHOLD = 2

# HARD-wall gate outcomes: a gate produced POSITIVE evidence the page is walled
# (anti-bot fingerprint, a matched block page, a paywall, or a near-empty shell).
# Scanned across the WHOLE log — not just the last gate — because a marker-less
# thin regate can sit DOWNSTREAM of one of these (a browser that failed to solve
# a Turnstile challenge and landed on a bespoke stub). Keying on the last gate
# alone would launder that real wall into `thin_unverified` — the exact
# projection-not-observation trap this module exists to prevent. `length_floor`
# and `other` are deliberately NOT here: bare thinness is corroboration-keyed
# (see `classify_terminal`) and `other` falls to the default `wall`.
_HARD_WALL_GATE_VERDICTS = frozenset(
    {
        Verdict.block_page_detected,
        Verdict.anti_bot,
        Verdict.paywall,
        Verdict.blank_page,
    }
)


# Gate subsystems that fingerprint a thin page as a SHELL / non-bare miss, not a
# genuinely small complete page: a JS-required SPA shell, a known JS-heavy host's
# thin browser response, or an empty-result marker. `length_floor` carrying any of
# these is NOT a bare thin fallthrough — the complete-small-page promotion must
# exclude it (an under-rendered SPA is a wall-shaped miss, not a tiny page), and the
# planner keeps the full robust-render budget for it (a distinct engine is a legit
# second attempt on a shell).
_SHELL_FINGERPRINT_SUBSYSTEMS = frozenset({"js_required", "thin_browser_response", "empty_result"})


def has_hard_wall_evidence(observations: Sequence[Observation]) -> bool:
    """True if ANY gate observation in the whole log is a hard-wall verdict."""
    return any(o.kind is ObservationKind.gate_outcome and o.verdict in _HARD_WALL_GATE_VERDICTS for o in observations)


def has_shell_fingerprint(observations: Sequence[Observation]) -> bool:
    """True if ANY gate observation fingerprinted a thin page as a shell/non-bare
    miss (`js_required` / `thin_browser_response` / `empty_result`). Distinct from
    `has_hard_wall_evidence`: these ride on a `length_floor` verdict (a soft thin
    signal) rather than a hard-wall verdict, but they still mean the thin page is
    NOT a genuinely small complete one."""
    return any(o.kind is ObservationKind.gate_outcome and o.subsystem in _SHELL_FINGERPRINT_SUBSYSTEMS for o in observations)


def has_subresource_block_evidence(observations: Sequence[Observation]) -> bool:
    """True if ANY observation recorded a challenged page subresource during render.

    Positive `subresource_blocks` means a browser watched a page XHR/fetch get
    challenged (401/403/429) — the walled-API fake-empty: the shell can 200 and
    render an authentic "0 results" while its data API is blocked. Non-text,
    adversary-hard evidence; the only signal that separates that from a true empty.
    """
    return any(o.subresource_blocks > 0 for o in observations)


def has_empty_marker(observations: Sequence[Observation]) -> bool:
    """True if the gate annotated a thin body as an empty result (`subsystem`)."""
    return any(o.kind is ObservationKind.gate_outcome and o.subsystem == "empty_result" for o in observations)


def _last_gate_verdict(observations: Sequence[Observation]) -> Verdict | None:
    """The most recent gate-outcome verdict, or None if the gate never ran."""
    for obs in reversed(observations):
        if obs.kind is ObservationKind.gate_outcome:
            return obs.verdict
    return None


def classify_terminal(observations: Sequence[Observation], resolved_verdict: Verdict) -> TerminalOutcome:
    """Map the decision log of a FAILED fetch to a `TerminalOutcome`.

    Pure and total. Called only when the fetch did not end `ok`. Precedence:
    operator error → unreachable → authoritative gone → subresource-block-anywhere
    → hard-wall-anywhere → corroborated not-found (read from the observations so it
    survives a mis-won resolved verdict) → lone not-found → empty_unverified (thin
    with an empty-result marker) → thin_unverified (thin, no marker) → wall (the
    default passable-obstacle floor).
    """
    if resolved_verdict is Verdict.paid_auth_error:
        return TerminalOutcome.operator_error
    if resolved_verdict in (Verdict.dns_error, Verdict.content_type_mismatch):
        return TerminalOutcome.unreachable

    # An authoritative handler "gone" is definitive regardless of anything else.
    if any(o.authoritative and o.verdict is Verdict.not_found for o in observations):
        return TerminalOutcome.gone_confirmed

    # A browser that watched a page subresource get challenged (walled-API
    # fake-empty) is POSITIVE, non-text wall evidence — it outranks a benign
    # rendered "0 results" body AND a stray 404 shell (the data API is blocked, so
    # content exists behind a wall). The only signal a text reader cannot fake.
    if has_subresource_block_evidence(observations):
        return TerminalOutcome.wall

    # POSITIVE wall evidence ANYWHERE in the log (whole-log scan) outranks a stray
    # uncorroborated not_found AND a marker-less thin regate downstream of it — a
    # browser that failed a challenge and landed on a bespoke thin stub is still a
    # wall. The page WAS reached and is walled; prescribe the browser.
    if has_hard_wall_evidence(observations):
        return TerminalOutcome.wall

    # not_found is keyed on what the cascade OBSERVED, not the projection: >=2
    # independent tiers seeing HTTP 404 is a confident miss; a single
    # uncorroborated 404 keeps the soft-404 caveat.
    not_found_obs = [o for o in observations if o.kind is ObservationKind.tier_outcome and o.verdict is Verdict.not_found]
    if len(not_found_obs) >= _CORROBORATION_THRESHOLD:
        return TerminalOutcome.gone_confirmed
    if not_found_obs:
        return TerminalOutcome.gone_unverified

    # A retrieved page that rendered thin (`length_floor` last gate) with no
    # hard-wall/subresource evidence and no 404: an empty result set or a minimal
    # page. The planner already escalated it to a real browser and it stayed thin,
    # so this is corroborated thin, not an untested ambiguity — an honest WARNING,
    # not the wall klaxon. When an empty-result marker matched, lean empty
    # (`empty_unverified`); otherwise stay agnostic (`thin_unverified`). Neither is
    # promoted to `ok` here — that is the orchestrator's `is_confirmed_empty`
    # conjunction, decided BEFORE this failure-only classifier. Bodyless transport
    # failures (timeout/connection_error/proxy) and `Verdict.other` have no thin
    # body to hand over and fall to `wall`.
    if _last_gate_verdict(observations) is Verdict.length_floor:
        if has_empty_marker(observations):
            return TerminalOutcome.empty_unverified
        return TerminalOutcome.thin_unverified

    return TerminalOutcome.wall


__all__ = [
    "TerminalOutcome",
    "classify_terminal",
    "has_empty_marker",
    "has_hard_wall_evidence",
    "has_shell_fingerprint",
    "has_subresource_block_evidence",
]
