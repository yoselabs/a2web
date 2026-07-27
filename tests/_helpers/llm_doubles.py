"""The declared-posture vocabulary for LLM test doubles.

A test double that ignores the prompt it is handed is not a witness. It reports
success while measuring nothing, and every assertion layered on top inherits the
blindness. This has now cost a real design decision: `_StubProvider` opened with
`del system, user`, so every wire golden and most `query` tests silently ran the
routing-LOST branch, and the ADR-0015 index signal was assessed as "fires on
every query — permanent noise" against a fixture rather than against a model.

So every LLM double declares what it IS. The declaration is mandatory, not
advisory: `tests/architecture/test_llm_double_fidelity.py` walks the suite and
fails on any double that does not carry one. Blindness is allowed — it is
undeclared blindness that is the defect, because that is what silently
substitutes a degraded branch for the healthy one.
"""

from __future__ import annotations

from enum import StrEnum


class DoubleArm(StrEnum):
    """What a given LLM double stands in for.

    Chosen so the declaration is a claim that can be CHECKED, not a label. The
    router arms mirror `RoutingOutcome` exactly, so a double claiming to
    exercise an arm can be run against the real extractor and verified to
    actually produce it.
    """

    #: Returns a recoverable router envelope when handed the router contract —
    #: the healthy path. MUST also provide `for_fidelity_check()`; this claim is
    #: verified behaviourally, because it is the claim that was false before.
    ROUTER_FAITHFUL = "router_faithful"

    #: Deliberately returns something the router parse cannot recover.
    UNPARSABLE = "unparsable"

    #: Deliberately returns a valid envelope with no classification.
    UNCLASSIFIED = "unclassified"

    #: Deliberately raises, or returns no usable completion.
    PROVIDER_ERROR = "provider_error"

    #: Doubles a DIFFERENT boundary entirely (judge, cache accounting, cost
    #: guard, token counting). Never reaches the router contract, so router
    #: fidelity is not a meaningful property of it.
    #:
    #: This is the escape hatch, and it is deliberately narrow: choosing it for
    #: a double that DOES reach the router path re-creates the original bug with
    #: a declaration attached. The reviewer's question for every use of this
    #: value is "is it really never used on a `query` path?"
    OFF_CONTRACT = "off_contract"


#: Doubles claiming a router arm must be constructible for verification.
FIDELITY_FACTORY = "for_fidelity_check"


def honor_contract(text: str, system: object) -> str:
    """Return what a real model would return for the contract in `system`.

    Most doubles are pass-throughs: the test hands them an `answer` string and
    they echo it. That makes the double's ARM a property of the call site rather
    than the class, which is unverifiable — and it is how prose ended up being
    returned on a path whose prompt says "Output strict JSON only".

    So pass-throughs route their text through here. Handed the router contract,
    prose is wrapped in a minimal valid envelope, exactly as a real model
    returns one. Anything already envelope-shaped is passed through untouched,
    so a test that deliberately supplies its own envelope (or deliberately
    supplies garbage to exercise the `unparsable` arm) still gets what it asked
    for.

    ONE implementation, imported by every double — copies would drift, and a
    drifted copy is indistinguishable from the bug being fixed.

    `system` is a TUPLE of prompt-cache blocks, not a str. `in` on the tuple
    tests element EQUALITY and silently never matches; the first attempt at this
    check shipped that exact bug. Hence `str(system)`.
    """
    import json

    if "structural_form" not in str(system):
        return text  # not the router contract — echo verbatim
    if not text.strip():
        # An empty answer is a legitimate state a test may be driving on purpose
        # (the `extraction_empty` -> `ask_unanswered` hard-fail path). A real
        # model that has nothing to say returns nothing; wrapping "" in an
        # envelope would manufacture a well-formed response out of a deliberate
        # emptiness and silently disarm those tests.
        return text
    if text.lstrip()[:1] in ("{", "["):
        return text  # caller supplied their own envelope; theirs wins
    return json.dumps({"answer": text, "structural_form": "article", "shape": "prose"})
