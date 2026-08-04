"""The response builder's slice of the fetch context is a BUDGET, not just a type.

**What moved, and what did not.** The slice used to be `_READS`, a hand-kept
frozenset of attribute names compared against the `fc.<name>` reads in
`fetcher_response.py` by an AST walk. It is now the `ResponseContext` Protocol
in that module, and `ty` checks it structurally at every call site. Verified by
mutation in all three directions before the ledger was deleted:

    rename `tier_used` on FetchContext   -> "Argument to build_response is incorrect"
    retype `small_page_confirmed`        -> "Argument to build_response is incorrect"
    read an undeclared field in builder  -> "ResponseContext has no attribute ..."

The type checker does strictly more than the ledger did. The ledger compared
NAMES, so it was blind to types — and that blindness was not hypothetical: the
Protocol's first draft annotated `routing` as `models.RouterPayload` and `ty`
rejected it, because the context carries the package-side
`llm_extract.RouterPayload`. Two different types, one spelling. A ledger of
names could never have said so.

**So why does this file still exist.** `ty` proves the slice is *correct*. It
has nothing to say about whether the slice is *small*. Adding twenty members to
the Protocol type-checks perfectly, and the original ledger's stated purpose was
the other thing:

    "What it prevents is the set growing silently until 'the response builder
    reads a bit of the context' quietly means 'the response builder reads most
    of it', which is the state that makes decomposition impossible to do
    safely."

That property has no type-level expression, so it is asserted here. This file is
now a budget guard and nothing else — correctness belongs to `make ty`.

**Do not restate the numbers in prose elsewhere.** The count lives in
`_MEMBER_CEILING` and in the Protocol itself. CLAUDE.md said "42 of 72" while
the old ledger held 45 names and its own docstring said "44 of 74" — three
numbers, one fact, none right. Cite this file.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_RESPONSE = _ROOT / "src" / "a2web" / "fetcher_response.py"
_CONTEXT = _ROOT / "src" / "a2web" / "fetcher" / "context.py"

#: The slice as of 2026-08-03, and a RATCHET rather than a target.
#:
#: Raising it is allowed and is sometimes right — but it must be deliberate,
#: because every member added here is one more thing
#: `decompose-fetcher-into-files` phase two has to keep together when it slices
#: `context.py` per node. If you are raising this, check whether the new read
#: could be a value passed in instead.
_MEMBER_CEILING = 45

#: Below this, the walk is broken rather than the code being wonderful.
_MEMBER_FLOOR = 30


def _protocol_members() -> set[str]:
    """Every member `ResponseContext` declares — annotated fields and methods."""
    tree = ast.parse(_RESPONSE.read_text(encoding="utf-8"))
    proto = next(c for c in ast.walk(tree) if isinstance(c, ast.ClassDef) and c.name == "ResponseContext")
    fields = {n.target.id for n in proto.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    methods = {n.name for n in proto.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    return fields | methods


def _context_members() -> set[str]:
    tree = ast.parse(_CONTEXT.read_text(encoding="utf-8"))
    cls = next(c for c in ast.walk(tree) if isinstance(c, ast.ClassDef) and c.name == "FetchContext")
    fields = {n.target.id for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    return fields | methods


def test_the_slice_has_not_grown_past_its_budget() -> None:
    members = _protocol_members()
    assert len(members) >= _MEMBER_FLOOR, (
        f"non-vacuous: parsed only {len(members)} members off `ResponseContext` — the AST walk broke, "
        "or the Protocol was renamed. This is not a pass."
    )
    assert len(members) <= _MEMBER_CEILING, (
        f"`ResponseContext` now declares {len(members)} members, budget is {_MEMBER_CEILING}.\n"
        "Every member is one more thing phase two must keep together when it slices "
        "`context.py` per node. Before raising `_MEMBER_CEILING`, check whether the new "
        "read could be a value passed in instead — that is the direction that unblocks "
        "the decomposition rather than deferring it further."
    )


def test_the_slice_is_a_minority_of_the_context() -> None:
    """The property the budget exists to preserve, stated directly.

    A ceiling alone drifts in meaning as `FetchContext` grows: 45 of 79 is a
    slice, 45 of 50 is "reads most of it" wearing the same number. The ratio is
    what makes decomposition tractable, so assert the ratio.
    """
    proto = _protocol_members()
    ctx = _context_members()
    assert len(ctx) >= 50, f"non-vacuous: parsed only {len(ctx)} FetchContext members"
    assert len(proto) < len(ctx) * 0.75, (
        f"the response builder now reads {len(proto)} of `FetchContext`'s {len(ctx)} members "
        f"({len(proto) / len(ctx):.0%}). Past ~three quarters this is not a slice, and "
        "`decompose-fetcher-into-files` phase two cannot cut the context per node without "
        "the response contract following it everywhere."
    )


def test_correctness_is_delegated_and_the_delegate_is_real() -> None:
    """Guard against this file quietly becoming the whole story again.

    The correctness half now rests entirely on `fc: ResponseContext` in the
    builder's signature. If that annotation is ever widened back to
    `FetchContext` — or to `Any` — `ty` stops checking the slice and this file
    would go on passing, reporting a budget for a boundary that no longer
    exists. That is the "reads as coverage while providing none" failure this
    repo keeps finding, so the delegation is asserted rather than assumed.
    """
    tree = ast.parse(_RESPONSE.read_text(encoding="utf-8"))
    builders = {
        n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in {"build_response", "_compose_next_links"}
    }
    assert builders, "neither `build_response` nor `_compose_next_links` was found — the walk broke"

    for name, fn in sorted(builders.items()):
        first = fn.args.args[0] if fn.args.args else None
        annotation = ast.unparse(first.annotation) if first is not None and first.annotation else None
        assert annotation == "ResponseContext", (
            f"`{name}` takes `{annotation}` rather than `ResponseContext`.\n"
            "The Protocol is what makes `ty` check the slice at every call site; widening "
            "this annotation silently retires that check and leaves only the budget below, "
            "which asserts nothing about correctness."
        )
