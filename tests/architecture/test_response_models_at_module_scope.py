"""Architectural invariant: pydantic `BaseModel` subclasses live at module scope.

a2kit antipattern #2 — class definitions inside function bodies confuse
fastmcp's schema generation. CLAUDE.md: "All return-type pydantic models at
module scope."
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "a2web"


def _is_basemodel_subclass(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "BaseModel":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
            return True
    return False


def _find_nested_basemodels(
    parent: ast.AST,
    rel_path: str,
    violations: list[str],
    *,
    inside_func_or_class: bool = False,
) -> None:
    for child in ast.iter_child_nodes(parent):
        if isinstance(child, ast.ClassDef):
            if inside_func_or_class and _is_basemodel_subclass(child):
                violations.append(
                    f"{rel_path}:{child.lineno}: `class {child.name}(BaseModel)` "
                    f"defined inside a function or another class — move to module scope"
                )
            # Recurse into class body, marking as nested.
            _find_nested_basemodels(
                child, rel_path, violations, inside_func_or_class=True
            )
        elif isinstance(child, ast.AsyncFunctionDef | ast.FunctionDef):
            _find_nested_basemodels(
                child, rel_path, violations, inside_func_or_class=True
            )
        else:
            _find_nested_basemodels(
                child, rel_path, violations, inside_func_or_class=inside_func_or_class
            )


def test_basemodels_at_module_scope() -> None:
    violations: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        rel = str(path.relative_to(_SRC_ROOT))
        source = path.read_text()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        _find_nested_basemodels(tree, rel, violations)

    assert not violations, (
        "Nested pydantic BaseModel detected. a2kit antipattern #2 — define at "
        "module scope:\n  " + "\n  ".join(violations)
    )
