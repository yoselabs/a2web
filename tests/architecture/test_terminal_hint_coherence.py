"""Architectural invariant: terminal outcome ↔ operator-hint coherence.

The incident this locks: a fetch shipped `verdict=length_floor` with a CRITICAL
`try_user_browser` hint on evidence that said `not_found` — an incoherent
combination (a dead URL dressed as an anti-bot wall). The three caller-facing
classification channels (`Verdict` / `Obstacle` / `OperatorHint`) are deliberately
NOT collapsed (different layers, producers, reliabilities), but they must relate
by a declared, tested table so an incoherent combination cannot ship again.

This asserts the relation between `TerminalOutcome` and the operator-hint codes
it may emit:
  - totality: every `TerminalOutcome` member has a declared policy (a new member
    fails CI here until its terminal hint is decided);
  - mutual exclusion: the wall prescription (`try_user_browser`) and the gone
    signal (`content_not_found`) are never both legal for one outcome — a dead
    URL is never also "behind a wall".
"""

from __future__ import annotations

from a2web.actions.terminal import TerminalOutcome

# The permitted terminal operator-hint codes per outcome. `None` in the set means
# "may legitimately emit no terminal hint" (an authoritative gone stays silent;
# operator_error carries its own `paid_auth_error` hint elsewhere; unreachable is
# honestly terminal). Keep this in lockstep with `fetcher._apply_terminal`.
_COHERENCE: dict[TerminalOutcome, frozenset[str | None]] = {
    TerminalOutcome.wall: frozenset({"try_user_browser"}),
    TerminalOutcome.gone_confirmed: frozenset({"content_not_found", None}),  # HTTP-corroborated info, or authoritative-silent
    TerminalOutcome.gone_unverified: frozenset({"content_not_found"}),
    TerminalOutcome.thin_unverified: frozenset({"content_thin"}),  # retrieved thin 200, no wall evidence
    TerminalOutcome.operator_error: frozenset({None}),  # paid_auth_error hint emitted at the paid tier
    TerminalOutcome.unreachable: frozenset({None}),
}

_WALL_HINT = "try_user_browser"
_GONE_HINT = "content_not_found"
_THIN_HINT = "content_thin"


def test_coherence_table_is_total_over_terminal_outcomes() -> None:
    """A new TerminalOutcome must declare its terminal-hint policy (fails CI otherwise)."""
    assert set(_COHERENCE) == set(TerminalOutcome)


def test_wall_and_gone_hints_are_mutually_exclusive() -> None:
    """No outcome may emit BOTH the anti-bot wall prescription AND the gone
    signal — the exact incoherence (`length_floor` + `try_user_browser` on
    `not_found` evidence) this table exists to forbid."""
    for outcome, codes in _COHERENCE.items():
        assert not ({_WALL_HINT, _GONE_HINT} <= codes), f"{outcome} may not emit both wall and gone hints"


def test_only_wall_prescribes_the_browser() -> None:
    """The critical `try_user_browser` klaxon is legal ONLY for `wall`."""
    for outcome, codes in _COHERENCE.items():
        if outcome is not TerminalOutcome.wall:
            assert _WALL_HINT not in codes, f"{outcome} must not prescribe the caller's browser"


def test_gone_signal_never_on_a_wall() -> None:
    """`content_not_found` is legal only for the two gone outcomes."""
    for outcome, codes in _COHERENCE.items():
        if outcome not in (TerminalOutcome.gone_confirmed, TerminalOutcome.gone_unverified):
            assert _GONE_HINT not in codes, f"{outcome} must not emit content_not_found"


def test_thin_signal_only_on_thin_unverified() -> None:
    """`content_thin` is legal ONLY for `thin_unverified` — a retrieved thin 200,
    never a wall (no klaxon) and never a dead URL (`content_not_found`)."""
    for outcome, codes in _COHERENCE.items():
        if outcome is not TerminalOutcome.thin_unverified:
            assert _THIN_HINT not in codes, f"{outcome} must not emit content_thin"
