"""No emitting site holds its own onward-link cap literal.

`openspec/specs/link-discovery/spec.md` states ONE invariant — "capped at 10
entries" — which was implemented as six independent literals: `arxiv.py`,
`hn.py`, `reddit.py`, `wikipedia._WIKILINK_CAP`,
`fetcher_response._NEXT_LINKS_CAP`, and `discourse._MAX_TOPICS` spelled `50`.

The sixth is why this guard exists rather than a comment. Discourse emitted
FIVE TIMES the stated cap, and `handler_probe.py` recorded `min_candidates=10,
# observed 30` as healthy — the baseline pinned the violation green, so the one
mechanism positioned to catch it instead certified it. The spec could not be
changed in one place because it had no one place.

This is the recurring shape: a bound re-implemented at N sites is the one
missing from the N+1th. The fix is a single `models.NEXT_LINKS_CAP`; this
forbids the next copy.

Scoped to sites that CONSTRUCT `NextLink`, because those are the sites that can
emit past the cap. A module that merely passes a list through cannot violate it.
"""

from __future__ import annotations

import ast

from ._walk import SRC_ROOT, walked_files

_MIN_FILES = 20

# A floor, not a frozen list. If the walk stops finding the sites that emit
# onward links, the guard is checking nothing and must fail rather than pass.
#
# `fetcher_response.py` is deliberately absent: it COMPOSES and caps link lists
# but constructs no `NextLink`, so it cannot emit past the cap — it is the site
# that applies it. The guard tracks producers, not the consumer.
_KNOWN_EMITTERS = frozenset({"arxiv.py", "hn.py", "reddit.py", "wikipedia.py", "discourse.py", "github.py"})

# Where the cap is allowed to be a literal — its single declaration.
_DECLARATION = "models.py"


def _emitting_functions() -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Functions that construct a `NextLink`, as `(filename, node)` pairs.

    Scoped to the FUNCTION rather than the file on purpose. `hn.py` bounds its
    rendered story list at 30 and `reddit.py` its post list at 25 — real bounds
    on how much BODY to show, in the same files that emit onward links. A
    file-level check flags those and the only way to stay green is to weaken the
    predicate until it catches nothing. The cap under test lives where the
    `NextLink` is built.
    """
    found: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for path in walked_files(SRC_ROOT, minimum=_MIN_FILES):
        if path.name == _DECLARATION:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            builds = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "NextLink" for n in ast.walk(node))
            if builds:
                found.append((path.name, node))
    return found


def test_the_cap_is_declared_exactly_once() -> None:
    source = (SRC_ROOT / _DECLARATION).read_text(encoding="utf-8")
    tree = ast.parse(source)
    declarations = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEXT_LINKS_CAP" for t in node.targets)
    ]
    assert len(declarations) == 1, f"NEXT_LINKS_CAP declared {len(declarations)} times in {_DECLARATION}"


def test_the_walk_found_the_emitting_sites() -> None:
    """Anti-vacuity: every assertion below is over this set."""
    emitters = {name for name, _ in _emitting_functions()}
    missing = _KNOWN_EMITTERS - emitters
    assert not missing, (
        f"the walk did not find the known NextLink emitters {sorted(missing)} "
        "(found: " + ", ".join(sorted(emitters)) + "). The parse broke, or a site "
        "stopped emitting — fix the walk rather than lowering the floor."
    )


def test_no_emitting_site_holds_its_own_cap_literal() -> None:
    """THE regression. Six literals; discourse's said 50 against a stated 10."""
    offenders: list[str] = []
    for filename, func in _emitting_functions():
        name = f"{filename}::{func.name}"
        for node in ast.walk(func):
            # `entries[:10]`, `hits[:50]` — a slice bound written as a number.
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
                upper = node.slice.upper
                if isinstance(upper, ast.Constant) and isinstance(upper.value, int):
                    offenders.append(f"{name}: slice bound [:{upper.value}]")
            # `if len(out) >= 10: break` — a length comparison against a number.
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Call):
                called = node.left.func
                if isinstance(called, ast.Name) and called.id == "len":
                    for comparator in node.comparators:
                        if isinstance(comparator, ast.Constant) and isinstance(comparator.value, int) and comparator.value > 1:
                            offenders.append(f"{name}: len(...) compared to {comparator.value}")

    assert not offenders, (
        "onward-link cap written as a literal at an emitting site:\n  "
        + "\n  ".join(offenders)
        + "\n\nImport `NEXT_LINKS_CAP` from `models` instead. The spec states one "
        "cap; it needs one implementation. A site that legitimately bounds "
        "something ELSE (a body render cap) should name that bound — see "
        "`discourse._MAX_TOPICS`, which is a render cap and is not this."
    )


def test_the_guard_can_see_a_reintroduced_literal() -> None:
    """Anti-vacuity: the detector must fire on the shape it claims to catch.

    Without this, `test_no_emitting_site_holds_its_own_cap_literal` passes
    identically whether the AST predicates work or match nothing at all — which
    is exactly how the previous six literals survived.
    """
    tree = ast.parse("out = entries[:10]\nif len(acc) >= 50:\n    pass\n")
    slices = [n for n in ast.walk(tree) if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice)]
    assert slices, "the slice predicate no longer matches `entries[:10]`"
    upper = slices[0].slice.upper  # type: ignore[union-attr]
    assert isinstance(upper, ast.Constant) and upper.value == 10

    compares = [n for n in ast.walk(tree) if isinstance(n, ast.Compare) and isinstance(n.left, ast.Call)]
    assert compares, "the len-comparison predicate no longer matches `len(acc) >= 50`"
