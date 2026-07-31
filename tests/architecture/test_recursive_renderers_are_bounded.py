"""Every handler that renders a recursive structure must bound its depth.

Handler trees come from the network — a comment tree, a reply chain, a nested
post structure — so their shape is not a2web's to assume. `hn._render_kid`
walked the Algolia `children` tree with no cap: a thread nested past CPython's
~1000-frame limit raised `RecursionError` out of the handler, from a value a
stranger controls. `habr` and `discourse` had `_MAX_DEPTH` all along, which is
what makes the omission a drift rather than a design gap — the pattern existed
and one site was outside it.

Structural on purpose. Checking that each *known* renderer has a cap would go
green the moment a fourth handler is added without one, which is exactly how
this arrived: the guard has to find the renderers itself.
"""

from __future__ import annotations

import ast

from ._walk import SRC_ROOT, walked_files

_HANDLERS = SRC_ROOT / "handlers"

# Below the current population (9 handler modules) but far above zero.
_MIN_HANDLER_FILES = 6

# The three known tree-renderers. A floor, not a frozen list — a new bounded
# renderer should raise it, and a renderer disappearing from the walk means the
# detector stopped matching, not that the risk went away.
_MIN_RECURSIVE_RENDERERS = 3


def _self_recursive_depth_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    """Functions that take a `depth` parameter and call themselves.

    `depth` is the marker for "walks a nested structure"; self-recursion is what
    makes it unbounded-able. A loop-based walk over a flat, pre-tagged comment
    list (`_reddit_html`) is neither, and is correctly not matched.
    """
    out: list[ast.FunctionDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        args = node.args
        names = {a.arg for a in (*args.args, *args.kwonlyargs)}
        if "depth" not in names:
            continue
        calls_self = any(
            isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == node.name for inner in ast.walk(node)
        )
        if calls_self:
            out.append(node)
    return out


def _enforces_a_bound(func: ast.FunctionDef) -> bool:
    """Whether the function actually COMPARES against a bound.

    Not "mentions one". The first draft of this guard accepted the substring
    `budget` anywhere in the function — including the parameter name — and so
    stayed GREEN when the bound was deleted from the body, which is the exact
    failure mode the anti-vacuity rule exists to prevent. It has to be a
    comparison, because a comparison is the thing that can stop the recursion.
    """
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        dumped = ast.dump(node)
        if "_MAX_DEPTH" in dumped or "remaining" in dumped:
            return True
    return False


def test_every_recursive_handler_renderer_bounds_its_depth() -> None:
    found: list[tuple[str, str]] = []
    unbounded: list[str] = []

    for path in walked_files(_HANDLERS, minimum=_MIN_HANDLER_FILES):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_src = ast.dump(tree)
        for func in _self_recursive_depth_functions(tree):
            found.append((path.name, func.name))
            if "_MAX_DEPTH" not in module_src or not _enforces_a_bound(func):
                unbounded.append(f"{path.name}::{func.name}")

    assert len(found) >= _MIN_RECURSIVE_RENDERERS, (
        f"non-vacuous: expected at least {_MIN_RECURSIVE_RENDERERS} recursive "
        f"handler renderers, found {found}. The detector stopped matching — fix "
        "it rather than lowering the floor."
    )
    assert not unbounded, (
        f"unbounded recursive renderer(s) over untrusted remote input: {unbounded}. "
        "A network-supplied tree can nest past the interpreter's frame limit; "
        "bound it with `_MAX_DEPTH` (and a comment budget where deleted nodes "
        "do not advance depth), as hn/habr/discourse do."
    )


def test_the_detector_matches_the_three_known_renderers() -> None:
    """Anti-vacuity, sharper: name them, so a rename that silently drops one
    from the walk fails here rather than quietly shrinking the guard."""
    matched = set()
    for path in walked_files(_HANDLERS, minimum=_MIN_HANDLER_FILES):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in _self_recursive_depth_functions(tree):
            matched.add(f"{path.stem}::{func.name}")

    for expected in ("hn::_render_kid", "habr::_render_comment", "discourse::_render_post"):
        assert expected in matched, f"{expected} no longer matches the detector (matched: {sorted(matched)})"
