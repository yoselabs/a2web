"""Every declared hint code is built by a factory, and every factory lives in one place.

`HINT_CODES` closed the vocabulary and a validator made an undeclared code
impossible to construct. That was the SAFETY half. This is the other half: for
most of the vocabulary's life the *catalogue* was incomplete — eleven of the
twenty-four codes were built inline at their single call site, spread across
`fetcher.py`, `fetcher_response.py`, `tiers/browser.py` and `handlers/reddit.py`.

Why that matters and is not tidiness: these strings are what an agent is told
when a fetch fails. A reader auditing "what does a2web say when it cannot get a
page" found thirteen factories in `models.py` and reasonably assumed that was
the set. It was just over half of it, and the missing half included
`retrieval_incomplete` and `llm_unavailable` — two of the loudest ADR-0009
signals a2web emits.

Two of the eleven (`reddit_forbidden_try_archive`, `reddit_deleted_try_archive`)
were worse than merely scattered: they reached `OperatorHint` through a
`code=reason` PARAMETER, so they appeared in no census of `code="..."` at all.
They were discoverable only by reading `HINT_CODES` and noticing nothing built
them — which is exactly what a closed vocabulary is for, and why this guard
asserts over that set rather than over whatever the source happens to contain.
"""

from __future__ import annotations

import ast
import inspect

import pytest

import a2web.hints as hints
from a2web.hints import HINT_CODES, OperatorHint, has_hint

from ._walk import SRC_ROOT

#: Codes whose factory takes required arguments the guard cannot invent. Listed
#: so the "can it actually be constructed" check below still covers them via
#: introspection rather than being skipped silently.
_FACTORY_SUFFIX = "_hint"


def _factories() -> dict[str, object]:
    return {name: fn for name, fn in inspect.getmembers(hints, inspect.isfunction) if name.endswith(_FACTORY_SUFFIX)}


def test_the_census_is_not_vacuous() -> None:
    """A guard that found no factories would pass every assertion below."""
    found = _factories()
    assert len(found) >= 20, f"found only {len(found)} hint factories in hints.py — the census is not reading it"
    assert len(HINT_CODES) >= 20, f"HINT_CODES holds {len(HINT_CODES)} codes — the vocabulary is not being read"


def test_every_declared_code_is_emitted_by_a_factory() -> None:
    """THE regression. Eleven codes had no factory and were built at call sites."""
    source = inspect.getsource(hints)
    emitted = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.keyword) and node.arg == "code" and isinstance(node.value, ast.Constant)
        for node in [node.value]
        if isinstance(node.value, str)
    }
    missing = sorted(HINT_CODES - emitted)
    assert not missing, (
        "declared hint codes that no factory in hints.py builds:\n"
        + "".join(f"  {code}\n" for code in missing)
        + "\nA code with no factory gets constructed inline at its call site, so "
        "its wording lives wherever it happens to be built and the catalogue a "
        "reader sees is incomplete. Add a factory here."
    )


def test_no_operator_hint_is_constructed_outside_the_catalogue() -> None:
    """The rule that keeps the catalogue complete once it is complete.

    Without this, the next hint gets written inline exactly like the last eleven
    and the guard above stays green — because it asks whether every declared code
    has a factory, not whether anything ELSE also builds hints.
    """
    offenders: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path.name == "hints.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "OperatorHint":
                offenders.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno}")

    assert not offenders, (
        "`OperatorHint(...)` constructed outside hints.py:\n"
        + "".join(f"  {site}\n" for site in offenders)
        + "\nOperator-hint copy is what an agent is told when a fetch fails; it "
        "belongs in the one catalogue, not at the call site. Add a factory to "
        "hints.py and call it from here."
    )


@pytest.mark.parametrize("code", sorted(HINT_CODES))
def test_every_declared_code_is_constructible(code: str) -> None:
    """A declared code that `OperatorHint` rejects would be a dead vocabulary entry."""
    assert OperatorHint(code=code, message="x").code == code


def test_has_hint_rejects_a_code_outside_the_vocabulary() -> None:
    """The asymmetric half: a lookup that silently answers False is the worse bug.

    Construction was already protected — an undeclared code raises. A DISPATCH
    comparing a bare string does not raise when the code is misspelled or later
    renamed; it returns False forever and the branch it guards quietly stops
    running, with nothing reporting it.
    """
    hints = [OperatorHint(code="content_thin", message="x")]
    assert has_hint(hints, "content_thin") is True
    assert has_hint(hints, "llm_unavailable") is False

    with pytest.raises(ValueError, match="not in the closed HINT_CODES"):
        has_hint(hints, "content_thn")


def test_no_dispatch_site_compares_a_bare_code_string() -> None:
    """`h.code == "..."` must go through `has_hint`, which validates the code."""
    offenders: list[str] = []
    checked = 0
    for path in sorted(SRC_ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Compare):
                continue
            left = node.left
            if not (isinstance(left, ast.Attribute) and left.attr == "code"):
                continue
            checked += 1
            # `hints.has_hint` IS the validated implementation; it is allowed
            # to do the comparison everyone else must route through it.
            if path.name == "hints.py":
                continue
            offenders.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno}")

    assert checked >= 1, "found no `.code ==` comparisons at all — the AST walk is not reading the tree"
    assert not offenders, (
        "operator-hint code compared as a bare string:\n"
        + "".join(f"  {site}\n" for site in offenders)
        + "\nUse `has_hint(hints, code)` — it validates the code against the "
        "vocabulary, so a rename fails loudly instead of matching nothing."
    )
