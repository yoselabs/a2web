"""Architectural invariant: provider-selection policy has one source of truth.

The fallback preference order `("claude-code", "anthropic")` and the
`_manifests.llm_providers` surface path used to be hand-copied across
`llm_resource._build` and `llm_eval/__main__._pick_provider`. After
`centralize-provider-selection` both live exactly once, in `llm_resource.py`'s
`select_provider`. This test fails CI on the first commit that re-introduces a
second copy (the duplication this change was made to remove).
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "a2web"

_SURFACE_STRING = "a2web._manifests.llm_providers"
_ORDER_TUPLE = ("claude-code", "anthropic")


def _str_tuple(node: ast.AST) -> tuple[str, ...] | None:
    """Return the value of an `(str, str, ...)` literal, else None."""
    if not isinstance(node, ast.Tuple):
        return None
    out: list[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.append(elt.value)
        else:
            return None
    return tuple(out)


def _scan() -> tuple[list[str], list[str]]:
    surface_hits: list[str] = []
    order_hits: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        rel = str(path.relative_to(_SRC_ROOT))
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == _SURFACE_STRING:
                surface_hits.append(f"{rel}:{node.lineno}")
            elif _str_tuple(node) == _ORDER_TUPLE:
                order_hits.append(f"{rel}:{node.lineno}")
    return surface_hits, order_hits


def test_provider_surface_string_declared_once() -> None:
    surface_hits, _ = _scan()
    assert len(surface_hits) == 1, (
        f'the provider surface "{_SURFACE_STRING}" must be declared exactly once '
        f"(in llm_resource.select_provider); found: {surface_hits}"
    )


def test_provider_order_tuple_declared_once() -> None:
    _, order_hits = _scan()
    assert len(order_hits) == 1, (
        f"the provider fallback order {_ORDER_TUPLE} must be declared exactly once "
        f"(in llm_resource._PROVIDER_ORDER); found: {order_hits}"
    )
