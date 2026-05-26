"""Architectural invariant: plugin manifest files have no module-level side effects.

`load_surface(...)` imports every module under `_manifests/<surface>/` at boot.
Module-level work (network calls, singleton construction, prints, mutating
state) would fire at import time even for plugins that the registry later
filters out as Unavailable. Plugin files must consist of: imports, function
defs, class defs, MANIFEST = PluginManifest(...). Nothing else.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFESTS_ROOT = _REPO_ROOT / "src" / "a2web" / "_manifests"


def _is_acceptable_module_statement(stmt: ast.stmt) -> bool:
    """Allow imports, defs, the MANIFEST = ... assignment, and string-only
    docstring/ellipsis-only top-level statements."""
    if isinstance(
        stmt,
        ast.Import | ast.ImportFrom | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ):
        return True
    if isinstance(stmt, ast.AnnAssign):
        # Bare type-annotation (e.g. `MANIFEST: PluginManifest = ...`)
        return True
    if isinstance(stmt, ast.Assign):
        # Top-level Name = expression. Allow only when the LHS is `MANIFEST`
        # or starts with `_` (private constants are common: pricing tables,
        # internal singletons defined by the plugin file).
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                if target.id != "MANIFEST" and not target.id.startswith("_"):
                    return False
            else:
                return False
        return True
    if isinstance(stmt, ast.Expr):
        # Module docstring (string literal) is fine. Bare expressions (calls,
        # etc.) are NOT — they're side effects.
        return isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
    if isinstance(stmt, ast.If) and _is_typing_only_if(stmt):
        return True
    return False


def _is_typing_only_if(stmt: ast.If) -> bool:
    """Allow `if TYPE_CHECKING: ...` blocks at module level."""
    test = stmt.test
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


def test_plugin_modules_only_declare_manifest() -> None:
    violations: list[str] = []
    for path in _MANIFESTS_ROOT.rglob("*.py"):
        # Skip __init__.py — those legitimately carry surface-level glue
        # (Sink protocol alias, EvalSystemContext dataclass).
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(_REPO_ROOT)
        source = path.read_text()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for stmt in tree.body:
            if not _is_acceptable_module_statement(stmt):
                violations.append(
                    f"{rel}:{stmt.lineno}: {type(stmt).__name__} at module scope "
                    f"— plugin files may only declare imports, defs, classes, "
                    f"and MANIFEST/private (_-prefixed) assignments"
                )

    assert not violations, (
        "Side-effect at module scope in plugin file:\n  " + "\n  ".join(violations)
    )
