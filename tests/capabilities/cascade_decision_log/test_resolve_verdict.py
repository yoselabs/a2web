"""Property + example tests for `resolve_verdict` — the cascade-decision-log projection.

The load-bearing invariant is **order-independence**: a verdict can never be
lost by arrival order, because there is no mutable slot to clobber.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from a2web.decision_log import Observation, ObservationKind, resolve_verdict
from a2web.models import Verdict

_observations = st.builds(
    Observation,
    kind=st.sampled_from(ObservationKind),
    source=st.text(max_size=20),
    verdict=st.sampled_from(Verdict),
    authoritative=st.booleans(),
    t_ms=st.integers(min_value=0, max_value=600_000),
)
_logs = st.lists(_observations, max_size=12)


@given(_logs)
def test_resolve_is_total(log: list[Observation]) -> None:
    """Every possible log yields a defined `Verdict` member — never an error."""
    assert resolve_verdict(log) in set(Verdict)


@given(_logs, st.data())
def test_resolve_is_order_independent(log: list[Observation], data: st.DataObject) -> None:
    """The result depends on the set of observations, not their arrival order."""
    permuted = data.draw(st.permutations(log))
    assert resolve_verdict(permuted) == resolve_verdict(log)


@given(_logs, _observations)
def test_resolve_is_idempotent_under_duplicates(log: list[Observation], obs: Observation) -> None:
    """A duplicated observation does not change the result."""
    assert resolve_verdict([*log, obs]) == resolve_verdict([*log, obs, obs])


def test_empty_log_resolves_to_other() -> None:
    """The empty log is a defined case, not an edge case."""
    assert resolve_verdict([]) == Verdict.other


def test_gate_pass_always_wins() -> None:
    """A gate-passing observation yields ok regardless of earlier failures."""
    log = [
        Observation(ObservationKind.tier_outcome, "site_handler", Verdict.not_found, True, 1),
        Observation(ObservationKind.tier_outcome, "raw", Verdict.ok, False, 2),
        Observation(ObservationKind.gate_outcome, "gate", Verdict.ok, False, 3),
    ]
    assert resolve_verdict(log) == Verdict.ok


def test_authoritative_not_found_outranks_downstream_length_floor() -> None:
    """A site handler's authoritative not_found beats a generic tier's length_floor.

    This is the `handler-verdict-precedence` behavior, now a uniform projection
    rule rather than a bespoke reconciliation phase.
    """
    log = [
        Observation(ObservationKind.tier_outcome, "site_handler", Verdict.not_found, True, 1),
        Observation(ObservationKind.tier_outcome, "raw", Verdict.ok, False, 2),
        Observation(ObservationKind.gate_outcome, "gate", Verdict.length_floor, False, 3),
    ]
    assert resolve_verdict(log) == Verdict.not_found


def test_downstream_recovery_beats_earlier_authoritative_failure() -> None:
    """A later gate-passing observation beats an earlier authoritative not_found."""
    log = [
        Observation(ObservationKind.tier_outcome, "site_handler", Verdict.not_found, True, 1),
        Observation(ObservationKind.gate_outcome, "gate", Verdict.ok, False, 2),
    ]
    assert resolve_verdict(log) == Verdict.ok


def test_all_tiers_fail_picks_highest_precedence() -> None:
    """With no win, the highest-precedence failed-tier verdict wins."""
    log = [
        Observation(ObservationKind.tier_outcome, "raw", Verdict.connection_error, False, 1),
        Observation(ObservationKind.tier_outcome, "jina", Verdict.timeout, False, 2),
    ]
    assert resolve_verdict(log) == Verdict.connection_error


def test_won_tier_with_failing_gate_resolves_to_gate_verdict() -> None:
    """A tier wins, the gate downgrades it — the gate verdict stands."""
    log = [
        Observation(ObservationKind.tier_outcome, "raw", Verdict.ok, False, 1),
        Observation(ObservationKind.gate_outcome, "gate", Verdict.length_floor, False, 2),
    ]
    assert resolve_verdict(log) == Verdict.length_floor
