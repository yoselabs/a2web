"""Unit tests for `classify_terminal` — the pure terminal-story classifier."""

from __future__ import annotations

from a2web.actions.terminal import TerminalOutcome, classify_terminal
from a2web.decision_log import Observation, ObservationKind
from a2web.models import Verdict


def _tier(verdict: Verdict, *, authoritative: bool = False, status_code: int = 0) -> Observation:
    return Observation(
        kind=ObservationKind.tier_outcome,
        source="raw",
        verdict=verdict,
        authoritative=authoritative,
        t_ms=1,
        status_code=status_code,
    )


def _gate(verdict: Verdict) -> Observation:
    return Observation(kind=ObservationKind.gate_outcome, source="gate", verdict=verdict, authoritative=False, t_ms=2)


def test_two_independent_404s_are_gone_confirmed() -> None:
    log = [_tier(Verdict.not_found, status_code=404), _tier(Verdict.not_found, status_code=404)]
    assert classify_terminal(log, Verdict.not_found) is TerminalOutcome.gone_confirmed


def test_single_404_is_gone_unverified() -> None:
    log = [_tier(Verdict.not_found, status_code=404)]
    assert classify_terminal(log, Verdict.not_found) is TerminalOutcome.gone_unverified


def test_authoritative_not_found_is_gone_confirmed_even_alone() -> None:
    log = [_tier(Verdict.not_found, authoritative=True, status_code=404)]
    assert classify_terminal(log, Verdict.not_found) is TerminalOutcome.gone_confirmed


def test_wall_gate_outranks_stray_uncorroborated_404() -> None:
    # A handler escalate_to_render placeholder 404 co-occurring with a browser-
    # rendered block page: the page WAS reached and is walled → prescribe browser.
    log = [_tier(Verdict.not_found, status_code=404), _gate(Verdict.block_page_detected)]
    assert classify_terminal(log, Verdict.not_found) is TerminalOutcome.wall


def test_corroborated_404_survives_a_miswon_resolved_verdict() -> None:
    # Bug-2 regression: two 404 observations must be reachable even when the
    # resolved verdict is a mis-won thin tier (no wall gate present).
    log = [_tier(Verdict.not_found, status_code=404), _tier(Verdict.not_found, status_code=404)]
    assert classify_terminal(log, Verdict.length_floor) is TerminalOutcome.gone_confirmed


def test_content_wall_is_wall() -> None:
    log = [_tier(Verdict.connection_error, status_code=403), _gate(Verdict.anti_bot)]
    assert classify_terminal(log, Verdict.anti_bot) is TerminalOutcome.wall


def test_paid_auth_error_is_operator_error() -> None:
    log = [_tier(Verdict.paid_auth_error, authoritative=True)]
    assert classify_terminal(log, Verdict.paid_auth_error) is TerminalOutcome.operator_error


def test_dns_and_content_type_mismatch_are_unreachable() -> None:
    assert classify_terminal([_tier(Verdict.dns_error)], Verdict.dns_error) is TerminalOutcome.unreachable
    assert classify_terminal([_tier(Verdict.content_type_mismatch)], Verdict.content_type_mismatch) is TerminalOutcome.unreachable


def test_bare_transport_failure_is_wall() -> None:
    log = [_tier(Verdict.timeout)]
    assert classify_terminal(log, Verdict.timeout) is TerminalOutcome.wall
