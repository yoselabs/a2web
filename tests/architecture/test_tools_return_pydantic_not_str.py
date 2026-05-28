"""Architectural invariant: `@a2kit.read` / `@a2kit.write` tools never
return `-> str`.

CLAUDE.md: "Don't return `-> str` from a tool. Return dict / pydantic model."
MCP clients parse return values — a plain string gives the agent nothing
to introspect.

Tach can't see this; the decorator + return-annotation pair is a call-site
+ signature rule that needs AST.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "a2web"

_TOOL_DECORATORS: frozenset[str] = frozenset({"read", "write"})


def _is_tool_decorator(dec: ast.expr) -> bool:
    """Match `@a2kit.read`, `@a2kit.read(...)`, `@a2kit.write`, etc."""
    if isinstance(dec, ast.Call):
        return _is_tool_decorator(dec.func)
    if isinstance(dec, ast.Attribute):
        if isinstance(dec.value, ast.Name) and dec.value.id == "a2kit":
            return dec.attr in _TOOL_DECORATORS
    return False


def _returns_str(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    if isinstance(annotation, ast.Name) and annotation.id == "str":
        return True
    # str | None / Optional[str] also banned for tools.
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _returns_str(annotation.left) or _returns_str(annotation.right)
    return False


def test_no_tool_returns_str() -> None:
    violations: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        rel = str(path.relative_to(_SRC_ROOT))
        source = path.read_text()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            if not any(_is_tool_decorator(d) for d in node.decorator_list):
                continue
            if _returns_str(node.returns):
                violations.append(
                    f"{rel}:{node.lineno}: tool `{node.name}` returns `str` — return a dict or pydantic model so MCP clients can introspect"
                )

    assert not violations, "Tool returns bare `str`. CLAUDE.md ban — declare a typed response:\n  " + "\n  ".join(violations)
