"""The CONTENT half of a retrieval result has exactly two writers, one per provenance.

`tests/architecture/test_transport_install_chokepoint.py` pins `body`,
`content_type`, `final_url`, `tier_used`, `status_code` and
`pre_rendered_payload` to a single `install()` call. This file pins the other
half — the five fields that mirror `Rendered` — and the ordering is worth
stating plainly, because it is backwards from what the incident record implies.

**The live bug happened in THIS set, and this set is the one that stayed
unguarded.** `links` was added to one of four copies of the content install, so
the fix meant to make `other_pages` reachable did nothing on the common
escalation path (a handler wins, the gate says `length_floor`, the browser
escalates). Measured on `arxiv.org/list/cs.CL/recent` after that fix shipped:
`fc.links == 0`. The response was `_install_rendered_fields`, whose docstring
says **"THE ONLY PLACE THIS COPY IS WRITTEN"** — and then the guard that got
written covered the transport fields instead. So the sentence carrying the
incident has been an unbacked claim ever since, in a repo whose standing rule is
that a claim the code does not back is the thing to go looking for.

**And read strictly, it is false.** `_phase_extract` writes the same five
fields from a fresh trafilatura result. That is not a bug — it is the second
provenance, and the two are mutually exclusive by construction (the pre-rendered
branch returns before reaching it). What the docstring means is "the only place
the PRE-RENDERED copy is written". What it says is stronger, and a reader adding
a third path has no way to tell which reading was intended. This guard states
the true invariant instead: **two full writers, one per provenance, plus one
narrowing partial** — and a third is the regression.

Why not collapse the two into one function anyway: they do not write the same
thing. `_phase_extract` also sets `published` and `meta_dict`, which `Rendered`
does not carry, because a pre-rendering tier never parsed HTML metadata. Forcing
one writer would make it invent a clearing semantics for fields the other
provenance has no value for — the same reason `TierInstall` deliberately
excludes `etag` and the snapshot dates.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.architecture._walk import walked_files

_SRC = Path(__file__).resolve().parents[2] / "src" / "a2web"

#: The `Rendered` mirror. These five are exactly the fields
#: `_install_rendered_fields` copies, which is what makes a divergence between
#: the two provenances silent: both paths type-check, both look complete, and
#: the difference only shows up as a zero on a live page.
_CONTENT_FIELDS = frozenset({"content_md", "title", "byline", "headings", "links"})

#: Writers of the FULL set — one per provenance, and that is the whole design.
_FULL_WRITERS = {
    "_install_rendered_fields": "the pre-rendered provenance — a tier already ran the canonical extractor",
    "_phase_extract": "the raw provenance — trafilatura over `fc.body`, plus `published`/`meta_dict` that `Rendered` has no room for",
}

#: Writers of a PROPER SUBSET, which is a different act and is allowed to be one.
#: A rung that improves the body has no title or byline to offer and must not
#: clear them; that is `_run_extraction_escalation` replacing `content_md` alone.
#: Listed by the exact subset so it cannot quietly widen into a third full copy.
_PARTIAL_WRITERS = {
    "_run_extraction_escalation": frozenset({"content_md"}),
}

#: Assignments to `response.links` in `fetch()` are the wire object, not the
#: context. Scoping by receiver name is narrower than the transport guard's
#: any-`Name` rule on purpose: `content_md` and `title` are ordinary names on
#: `Rendered`, `ExtractResult` and both response models, so an unscoped walk
#: here reports the whole pipeline.
_CONTEXT_NAMES = frozenset({"fc"})


def _content_writes(node: ast.AST) -> set[str]:
    """Content fields assigned on the fetch context inside `node`."""
    written: set[str] = set()
    for sub in ast.walk(node):
        targets: list[ast.expr] = []
        if isinstance(sub, ast.Assign):
            targets = list(sub.targets)
        elif isinstance(sub, ast.AugAssign | ast.AnnAssign):
            targets = [sub.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr in _CONTENT_FIELDS
                and isinstance(target.value, ast.Name)
                and target.value.id in _CONTEXT_NAMES
            ):
                written.add(target.attr)
    return written


def _fetcher_functions() -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for path in walked_files(_SRC / "fetcher", minimum=5):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                found[node.name] = node
    return found


def test_only_the_two_provenances_write_the_content_half() -> None:
    functions = _fetcher_functions()
    assert len(functions) > 40, f"only {len(functions)} fetcher functions found — the walk is not seeing the tree"

    known = set(_FULL_WRITERS) | set(_PARTIAL_WRITERS)
    violations = [
        f"{name} writes {sorted(_content_writes(node))}"
        for name, node in functions.items()
        if name not in known and _content_writes(node)
    ]

    assert not violations, (
        "a third path writes the content half of a retrieval result:\n  "
        + "\n  ".join(violations)
        + "\nThere are two provenances — pre-rendered and freshly extracted — and each has "
        "one writer. A third copy is how `links` came to be set on one path of four, which "
        "made `other_pages` unreachable on the common escalation path while every test "
        "stayed green. Call `_install_rendered_fields`, or extend the provenance that owns "
        "this path."
    )


def test_both_provenances_write_the_whole_set() -> None:
    """The failure mode is a field added to one copy and not the other.

    Asserting each writes EXACTLY the declared set catches it in both
    directions: a sixth field added to `Rendered` and installed on only one
    path, and a field dropped from one path while the other keeps filling it.
    """
    functions = _fetcher_functions()
    for name, why in _FULL_WRITERS.items():
        assert name in functions, f"`{name}` not found — {why}; the writer moved or was renamed"
        assert _content_writes(functions[name]) == _CONTENT_FIELDS, (
            f"`{name}` no longer writes the whole content set: writes "
            f"{sorted(_content_writes(functions[name]))}, declared {sorted(_CONTENT_FIELDS)}.\n"
            "The two provenances must agree on the set or they disagree on a live page only."
        )


def test_every_partial_writer_still_writes_exactly_its_subset() -> None:
    """A partial that widens is a third full copy wearing an exemption."""
    functions = _fetcher_functions()
    for name, subset in _PARTIAL_WRITERS.items():
        assert name in functions, f"exempted partial writer `{name}` no longer exists"
        actual = _content_writes(functions[name])
        assert actual == subset, (
            f"`{name}` writes {sorted(actual)}, declared partial {sorted(subset)}.\n"
            "Widening a partial writer makes it a third full copy of the install. Narrowing "
            "it to nothing makes the exemption stale, which pre-authorises the next function "
            "to take that name."
        )
