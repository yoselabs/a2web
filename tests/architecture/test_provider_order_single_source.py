"""Architectural invariant: the provider preference order has one source of truth.

The auto-select order used to be a hand-copied string tuple across
`llm_resource` and `llm_eval/__main__`. It now lives once in `llm_resource` as a
tuple of `anyllm.ProviderName` members (`_PROVIDER_ORDER` / `_GATEWAY_FIRST_ORDER`),
and the bench imports it rather than restating it. This test fails CI on the
first commit that re-introduces a second copy.

The former `_manifests.llm_providers` surface-string check retired with the
manifest surface itself (v0.47): anyllm's `build_adapter` + `resolve_provider`
own provider construction now, so there is no surface path to keep singular.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._walk import walked_files

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "a2web"


def _is_provider_name_tuple(node: ast.AST) -> bool:
    """True for a `(ProviderName.X, ProviderName.Y, ...)` literal of ≥2 members."""
    if not isinstance(node, ast.Tuple) or len(node.elts) < 2:
        return False
    return all(isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id == "ProviderName" for e in node.elts)


def test_provider_order_tuple_declared_only_in_llm_resource() -> None:
    hits: list[str] = []
    for path in walked_files(_SRC_ROOT, minimum=80):
        rel = str(path.relative_to(_SRC_ROOT))
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if _is_provider_name_tuple(node):
                hits.append(f"{rel}:{node.lineno}")

    # `_PROVIDER_ORDER` + `_GATEWAY_FIRST_ORDER`, both in llm_resource.py.
    assert hits, "expected the ProviderName order tuple(s) in llm_resource.py — found none (did the walk break?)"
    offenders = [h for h in hits if not h.startswith("llm_resource.py:")]
    assert not offenders, f"provider order tuples must live only in llm_resource.py; found elsewhere: {offenders}"
