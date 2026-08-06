"""A `protects` marker names a real thing, or the suite refuses to say so quietly.

`scripts/spec_test_reconcile.py` is the one implementation of the join between
`@pytest.mark.protects(...)` markers and the requirements/ADRs/changes they
claim to name (design.md D6 of `openspec/changes/bind-tests-to-requirements`:
one parse, two consumers — a human report and this assertion — so they cannot
come to disagree). This guard calls it rather than re-walking the AST itself.

Two failure modes, both real:

  * a marker naming a requirement/ADR/change that does not exist reads as a
    decision while providing none, and is strictly worse than no marker
  * the traceable-requirement count drops below the committed floor, which
    can only happen by deleting the last citation of a requirement — a
    regression a plain test suite has no way to notice

Per the anti-vacuity rule (`tests/architecture/_walk.py`), a walk that finds
zero markers reads identical to a passing one. This asserts markers were
actually found.
"""

from __future__ import annotations

from scripts.spec_test_reconcile import TRACEABLE_REQUIREMENTS_FLOOR, reconcile

#: Below the count seeded in the change that introduced this guard (task 5 of
#: bind-tests-to-requirements/tasks.md) — ordinary future deletions of a
#: single marker should not trip this, but zero markers found at all means
#: the walk itself broke, not that nobody has used the marker yet.
_MINIMUM_MARKERS = 3


def test_every_protects_marker_resolves() -> None:
    rep = reconcile()
    unresolved = rep["markers"]["unresolved"]
    assert not unresolved, (
        "one or more @pytest.mark.protects(...) markers name an id that does "
        f"not exist: {unresolved}\n"
        "A marker naming a nonexistent requirement/ADR/change is worse than no "
        "marker — it reads as a decision while providing none. Fix the id, or "
        "remove the marker."
    )


def test_traceable_requirement_count_meets_the_floor() -> None:
    rep = reconcile()
    traceable = rep["totals"]["requirements_traceable_by_marker"]
    assert traceable >= TRACEABLE_REQUIREMENTS_FLOOR, (
        f"traceable requirements dropped to {traceable}, below the committed "
        f"floor of {TRACEABLE_REQUIREMENTS_FLOOR} in scripts/spec_test_reconcile.py.\n"
        "This regresses only when the last test citing a requirement is deleted "
        "or its marker removed. If the requirement was deliberately retired, "
        "lower the floor in the same change, with the reason recorded next to "
        "the value (openspec/specs/spec-test-traceability/spec.md)."
    )


def test_the_marker_walk_is_not_vacuous() -> None:
    rep = reconcile()
    total = rep["markers"]["total_markers"]
    assert total >= _MINIMUM_MARKERS, (
        f"the protects-marker walk found only {total} marker(s), expected at "
        f"least {_MINIMUM_MARKERS}.\n"
        "Either the AST walk broke (fix scripts/spec_test_reconcile.py) or "
        "every seeded marker was removed — an empty walk would make the two "
        "guards above pass vacuously, which is the one thing this test exists "
        "to prevent."
    )
