"""Cascade decision log — the append-only observation log and its projections.

One fetch accumulates an append-only sequence of `Observation` records. The
final verdict is a pure, total projection of that log via `resolve_verdict`:
nothing overwrites a prior observation, so an authoritative signal can never
be silently clobbered — it can only be out-prioritised by an explicit,
testable precedence rule.

Phase 1 of the `cascade-decision-log` change. The `decide_next` planner and
the full response projection arrive in Phase 2.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from .models import Verdict
from .packages.escalation import EscalationSignal


class ObservationKind(StrEnum):
    """What produced an observation."""

    tier_outcome = "tier_outcome"  # a tier / site-handler fetch attempt
    gate_outcome = "gate_outcome"  # a quality-gate evaluation of content


@dataclass(slots=True, frozen=True)
class Observation:
    """One immutable fact learned during a fetch — appended, never mutated.

    `authoritative` marks a verdict the producing source vouches is definitive
    for its domain (e.g. a site handler that confirmed a page is gone). An
    authoritative failure outranks every non-authoritative failure in
    `resolve_verdict`.
    """

    kind: ObservationKind
    source: str
    verdict: Verdict
    authoritative: bool
    t_ms: int
    # Evidence the planner (`decide_next`) reads to choose escalation.
    status_code: int = 0
    cloudflare: bool = False  # tier response came through Cloudflare
    # Typed escalation hint (Phase 4) — `escalation.next_tier` is a closed
    # Literal so the planner switches on values that type-check at compile
    # time. `escalation.reason` is a short diagnostic aligned with subsystem.
    escalation: EscalationSignal | None = None
    # Subsystem annotation from the producing source (e.g. block-detector
    # family name on gate observations: "js_required", "captcha_redirect",
    # "anubis"). Carried on the observation so the narrative / diagnostics
    # summary can read from the log projection, not from a mutable snapshot.
    subsystem: str | None = None


def _verdict_rank(verdict: Verdict) -> int:
    """Strict total precedence rank for a verdict — higher wins on failure.

    Exhaustive `match` closed with `assert_never`: adding a `Verdict` member
    breaks the build here until it is given a rank. Ranks are unique, so
    failure resolution is a total order and `resolve_verdict` is
    order-independent.
    """
    match verdict:
        case Verdict.paid_auth_error:
            # Highest precedence: a keyed paid service failing auth/billing is a
            # hard operator error that must surface, never be masked by a wall
            # verdict from a cheaper tier. Paired with `authoritative=True`.
            return 14
        case Verdict.dns_error:
            # A genuine DNS-resolution failure (NXDOMAIN): the domain does not
            # exist. Definitive and terminal — a real browser resolves the same
            # name identically, so there is nothing to escalate. Ranks just below
            # the operator-error paid_auth_error and above not_found (NXDOMAIN is
            # more definitive than a server-issued 404).
            return 13
        case Verdict.not_found:
            return 12
        case Verdict.paywall:
            return 11
        case Verdict.block_page_detected:
            return 10
        case Verdict.anti_bot:
            return 9
        case Verdict.blank_page:
            # An essentially-empty document surviving the full ladder (browser +
            # paid scraper both saw nothing). A wall-class terminal peer of
            # block_page_detected / anti_bot — a definitive miss, ranked just
            # below anti_bot and above rate_limited.
            return 8
        case Verdict.rate_limited:
            return 7
        case Verdict.content_type_mismatch:
            return 6
        case Verdict.proxy_unavailable:
            return 5
        case Verdict.connection_error:
            return 4
        case Verdict.timeout:
            return 3
        case Verdict.length_floor:
            return 2
        case Verdict.other:
            return 1
        case Verdict.ok:
            return 0
    assert_never(verdict)


def resolve_verdict(log: Sequence[Observation]) -> Verdict:
    """Derive the final verdict from the observation log.

    Pure, total, and order-independent — the result depends on the set of
    observations, not their arrival order. Precedence:

    1. Any gate-passing observation means the fetch succeeded → `ok` (a
       genuine downstream recovery always wins).
    2. A tier produced `ok` content but the gate never ran (empty body) → `ok`.
    3. Otherwise the highest-precedence failure verdict wins. An authoritative
       observation outranks any non-authoritative one; within each, the strict
       `_verdict_rank` order applies. Once a tier won, earlier failed-tier
       verdicts are moot — only the gate verdict and authoritative signals
       remain in contention.
    4. Empty log → `Verdict.other`.
    """
    gate_obs = [o for o in log if o.kind is ObservationKind.gate_outcome]
    if any(o.verdict is Verdict.ok for o in gate_obs):
        return Verdict.ok

    tier_obs = [o for o in log if o.kind is ObservationKind.tier_outcome]
    won = any(o.verdict is Verdict.ok for o in tier_obs)
    if won and not gate_obs:
        return Verdict.ok

    authoritative = [o for o in log if o.authoritative]
    if won:
        # A tier won — earlier failed-tier verdicts are moot; only the gate
        # verdict and any authoritative signal remain in contention.
        candidates = [*gate_obs, *authoritative]
    else:
        # No tier won — every failed tier attempt counts.
        candidates = [*(o for o in tier_obs if o.verdict is not Verdict.ok), *authoritative]
    if not candidates:
        return Verdict.other
    best = max(candidates, key=lambda o: (o.authoritative, _verdict_rank(o.verdict)))
    return best.verdict


__all__ = ("Observation", "ObservationKind", "resolve_verdict")
