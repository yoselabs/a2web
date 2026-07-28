"""The probe's case table is guarded offline, because the probe is not.

`make handler-probe` is live-network and runs on demand. Nothing in it stops a
floor from being edited to zero to turn a red run green — and that edit is
exactly the weakening that let a dead parser pass for months: an assertion made
weak enough that it could no longer fail.

So the SHAPE of the table is asserted here, in `make check`:

  - every registered handler has at least one case;
  - every handler that populates `next_links` has at least one case declaring a
    candidate floor above zero;
  - every case says what it checks.

**This is deliberately a weaker claim than "the floors are right."** An offline
suite cannot check a number against a live site — that is the probe's job, and
the two halves are not interchangeable. What this can check is that the number
was not DELETED, which is what happened last time.

The set of candidate-populating handlers is read from the handler sources by
AST rather than kept as a list here. A list would be a second thing to maintain,
and the failure mode of a stale list is that a handler quietly drops off it —
the same silence the guard exists to break.
"""

from __future__ import annotations

import ast
from pathlib import Path

from a2web.handler_probe import _PROBE_CASES
from a2web.handlers import _registry

#: Non-vacuity floors. A guard reporting "0 violations in 0 candidates" is
#: indistinguishable from a passing one and reads as coverage while providing
#: none — the repo's standing rule for structural guards.
_MIN_HANDLERS = 6
_MIN_CANDIDATE_HANDLERS = 5

_HANDLERS_DIR = Path(__file__).resolve().parents[3] / "src" / "a2web" / "handlers"


def _modules_populating_candidates() -> set[str]:
    """Handler module stems that pass `next_links=` somewhere.

    A heuristic, and knowingly one: a handler that built its candidates through
    an intermediate variable would be missed. That is a false NEGATIVE in a
    guard — it under-enforces rather than blocking correct code — and the
    probe's own loud-failure check still catches a handler absent from the table
    entirely.
    """
    found: set[str] = set()
    for path in _HANDLERS_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "next_links":
                found.add(path.stem)
                break
    return found


def _handler_name_for_module(stem: str) -> str:
    return f"site_handler:{stem}"


def test_the_walk_is_not_vacuous() -> None:
    """A guard that inspected nothing cannot object to anything."""
    assert len(_registry(None)) >= _MIN_HANDLERS
    populating = _modules_populating_candidates()
    assert len(populating) >= _MIN_CANDIDATE_HANDLERS, (
        f"only {len(populating)} handler modules appear to populate next_links: {sorted(populating)}. "
        "Either the handlers moved or the AST read stopped matching — both make the candidate-floor "
        "guard below vacuous."
    )


def test_every_registered_handler_has_a_case() -> None:
    registered = {h.name for h in _registry(None)}
    covered = {name for name, cases in _PROBE_CASES.items() if cases}
    missing = registered - covered
    assert not missing, (
        f"registered handlers with no probe case: {sorted(missing)}. A handler absent from the table "
        "is not probed at all — add a case per URL shape it serves."
    )


def test_every_case_says_what_it_checks() -> None:
    silent = [
        f"{name}[{case.shape}]" for name, cases in _PROBE_CASES.items() for case in cases if not case.checks.strip()
    ]
    assert not silent, (
        f"probe cases with no `checks` prose: {silent}. The field exists so a later reader can tell a "
        "deliberately weak assertion from an overlooked one; blank defeats it."
    )


def test_candidate_populating_handlers_declare_a_nonzero_floor() -> None:
    """A handler that builds an index must probe that it still does.

    Wikipedia is the case that motivates this. Its wikilink parse has no verdict
    guard and structurally cannot get one — the `dom_schema` container is
    `<body>`, which always matches, so a rotted selector reads as EMPTY rather
    than ROT. The probe's candidate floor is the ONLY live check that the parse
    still works. Zeroing it removes the last one.
    """
    registered = {h.name for h in _registry(None)}
    offenders: list[str] = []
    for stem in sorted(_modules_populating_candidates()):
        name = _handler_name_for_module(stem)
        if name not in registered:  # a helper module, not a registered handler
            continue
        cases = _PROBE_CASES.get(name, ())
        if not any(case.min_candidates > 0 for case in cases):
            offenders.append(name)
    assert not offenders, (
        f"handlers that populate next_links but declare no candidate floor: {offenders}. "
        "At least one case must assert min_candidates > 0, or a parse that stops yielding an index "
        "passes the probe silently — which is how the arXiv listing parser stayed green while dead."
    )
