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
# unreachable is honestly terminal). Keep this in lockstep with
# `fetcher._apply_terminal`.
#
# `operator_error` held `frozenset({None})` until 2026-07-31, commented
# "paid_auth_error hint emitted at the paid tier". NO SUCH HINT EXISTED. The
# guard was green because it had been told to expect nothing, on the strength of
# a claim nobody checked — and it would have stayed green through the hint's
# deletion, which is the state being fixed. An allowlist entry justified by a
# thing that does not exist is worse than no entry: it reads as a decision.
_COHERENCE: dict[TerminalOutcome, frozenset[str | None]] = {
    TerminalOutcome.wall: frozenset({"try_user_browser"}),
    TerminalOutcome.gone_confirmed: frozenset({"content_not_found", None}),  # HTTP-corroborated info, or authoritative-silent
    TerminalOutcome.gone_unverified: frozenset({"content_not_found"}),
    TerminalOutcome.thin_unverified: frozenset({"content_thin"}),  # retrieved thin 200, no wall evidence, no marker
    TerminalOutcome.empty_unverified: frozenset({"content_thin"}),  # thin 200 with an empty marker, uncorroborated
    TerminalOutcome.operator_error: frozenset({"paid_auth_error"}),  # emitted at the paid tier on a rejected key
    TerminalOutcome.unreachable: frozenset({None}),
}

_WALL_HINT = "try_user_browser"
_OPERATOR_HINT = "paid_auth_error"
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


def test_thin_signal_only_on_thin_or_empty_unverified() -> None:
    """`content_thin` is legal ONLY for the two retrieved-thin-200 outcomes
    (`thin_unverified` / `empty_unverified`) — never a wall (no klaxon) and never
    a dead URL (`content_not_found`)."""
    for outcome, codes in _COHERENCE.items():
        if outcome not in (TerminalOutcome.thin_unverified, TerminalOutcome.empty_unverified):
            assert _THIN_HINT not in codes, f"{outcome} must not emit content_thin"


def test_operator_error_requires_a_hint_that_actually_exists() -> None:
    """`operator_error` must demand a hint, and that hint must be constructible.

    Two assertions, because the failure had two halves. The table must not
    allow silence (it did, for as long as the claim went unchecked), AND the
    code it names must exist — an entry naming a hint nobody builds is the same
    green-for-nothing the `None` entry was.
    """
    codes = _COHERENCE[TerminalOutcome.operator_error]
    assert None not in codes, (
        "operator_error may not emit NO hint. A bad paid key is a retrieval "
        "failure the caller cannot route around; ADR-0009 requires it name the fix."
    )
    assert codes == frozenset({_OPERATOR_HINT})

    from a2web.hints import paid_auth_error_hint

    hint = paid_auth_error_hint("https://example.org/x", tier="zyte")
    assert hint.code == _OPERATOR_HINT, "the table names a code the factory does not produce"
    assert hint.severity == "critical" and hint.fix
