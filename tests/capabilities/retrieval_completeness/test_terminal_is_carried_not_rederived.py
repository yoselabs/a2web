"""`retrieval_incomplete` follows the terminal classification, not hint text.

`classify_terminal` decides the failure story once. `_apply_terminal` then
attached the matching hint and DISCARDED the classification, so the response
builder reconstructed it three times by reading the artifact back out — "is
there a `try_user_browser` hint", "is there a `content_not_found` at severity
`warning`", "is there a `content_thin`".

That made a hint's CODE and SEVERITY load-bearing for a decision they were never
meant to carry. Rewording a hint, or re-tuning a severity for how loud it should
read, could silently flip whether a fetch reported `retrieval_incomplete` — and
`retrieval_incomplete` is the ADR-0009 signal that stops a caller mistaking a
miss for a complete answer.

The classification is now carried on `FetchContext.terminal`. These tests pin
that the coupling is gone and that the behaviour it replaced is unchanged.
"""

from __future__ import annotations

import pytest

from a2web.actions.terminal import TerminalOutcome
from a2web.hints import OperatorHint

_INCOMPLETE = (
    TerminalOutcome.wall,
    TerminalOutcome.gone_unverified,
    TerminalOutcome.thin_unverified,
    TerminalOutcome.empty_unverified,
)
_COMPLETE = (TerminalOutcome.gone_confirmed, TerminalOutcome.operator_error, TerminalOutcome.unreachable)


def test_every_terminal_outcome_is_classified_one_way_or_the_other() -> None:
    """Anti-vacuity, and a real trap: a NEW outcome must not default to complete.

    An unlisted `TerminalOutcome` silently falls on the complete side, which is
    the ADR-0009 harm — a miss that reads as a finished job. This fails when
    someone adds one without deciding.
    """
    classified = {*_INCOMPLETE, *_COMPLETE}
    unclassified = sorted(o.name for o in TerminalOutcome if o not in classified)
    assert not unclassified, (
        f"TerminalOutcome value(s) not classified as complete or incomplete: {unclassified}. "
        "An unlisted outcome defaults to COMPLETE, which turns a miss into a finished job."
    )


@pytest.mark.parametrize("outcome", _INCOMPLETE, ids=lambda o: o.name)
def test_incomplete_outcomes_are_marked_incomplete(outcome: TerminalOutcome) -> None:
    from a2web.fetcher_response import _INCOMPLETE_TERMINALS

    assert outcome in _INCOMPLETE_TERMINALS


@pytest.mark.parametrize("outcome", _COMPLETE, ids=lambda o: o.name)
def test_confident_outcomes_are_not_marked_incomplete(outcome: TerminalOutcome) -> None:
    """A corroborated dead URL is a fact, not a miss. So is a bad paid key —
    which carries its own `paid_auth_error` hint rather than a browser klaxon."""
    from a2web.fetcher_response import _INCOMPLETE_TERMINALS

    assert outcome not in _INCOMPLETE_TERMINALS


def test_editing_hint_text_does_not_change_classification() -> None:
    """THE regression, stated as the property that was violated.

    A hint's message and fix are prose for a human and a model. They must have
    no bearing on whether the envelope reports a retrieval miss. Before the
    classification was carried, the presence and severity of specific hints WERE
    the decision.
    """
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[3] / "src" / "a2web" / "fetcher_response.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "build_response")
    body = ast.dump(fn)

    # `retrieval_incomplete` must not be decided by reading hint codes back out.
    for code in ("try_user_browser", "content_not_found", "content_thin"):
        assert f"'{code}'" not in body, (
            f"`build_response` still reads the {code!r} hint to decide incompleteness. "
            "Read `fc.terminal` — the classification `classify_terminal` already made."
        )


def test_a_hint_still_carries_its_own_severity() -> None:
    """Anti-vacuity: decoupling classification from hints must not flatten hints.

    The severity ladder is still real and still on the wire — it just no longer
    drives control flow.
    """
    from a2web.hints import try_user_browser_hint

    hint = try_user_browser_hint("https://example.com/walled")
    assert isinstance(hint, OperatorHint)
    assert hint.severity == "critical"
