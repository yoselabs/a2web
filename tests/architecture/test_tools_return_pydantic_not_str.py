"""Architectural invariant: an MCP tool never returns `-> str`.

CLAUDE.md: "Don't return `-> str` from a tool. Return dict / pydantic model."
MCP clients parse return values — a plain string gives the agent nothing to
introspect, and FastMCP has no output schema to publish for it.

Tach cannot see this; the decorator + return-annotation pair is a call-site +
signature rule that needs AST.

**This test was vacuously green through the whole a2kit sunset.** It matched
`@a2kit.read` / `@a2kit.write`, decorators that stopped existing in Phase 4.
The walk still visited 119 files and still passed — it just never found a tool
to inspect. The `walked_files` floor added in 6.7 does not catch this: it
proves the *files* were walked, not that anything inside them matched.

So the fix is two-part, and the second half is the one that matters:

1. Match what a2web actually writes now — `@mcp.tool(...)`.
2. Assert the walk found tools at all. A structural guard that reports
   "0 violations found in 0 candidates" is indistinguishable from a passing
   one, and reads as coverage while providing none.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._walk import walked_files

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "a2web"

#: Every tool a2web registers today (`query`, `fetch_raw`, `refresh`). The floor
#: sits below that so adding or removing one tool does not trip it — it catches
#: "the matcher stopped matching anything", which is the failure this test has
#: already had once.
_MINIMUM_TOOLS = 2


def _is_tool_decorator(dec: ast.expr) -> bool:
    """Match `@mcp.tool`, `@mcp.tool(...)`, `@server.tool(name=…)`.

    Matches on the *attribute* rather than the receiver's name, so a future
    registration that binds the server to some other local name still counts.
    Over-matching is the safe direction here: a false positive is a visible
    failure, a false negative is silence.
    """
    if isinstance(dec, ast.Call):
        return _is_tool_decorator(dec.func)
    if isinstance(dec, ast.Attribute):
        return dec.attr == "tool"
    return False


def _returns_str(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    if isinstance(annotation, ast.Name) and annotation.id == "str":
        return True
    if isinstance(annotation, ast.Constant) and annotation.value == "str":
        return True  # `from __future__ import annotations` stringifies these
    # str | None / Optional[str] also banned for tools.
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _returns_str(annotation.left) or _returns_str(annotation.right)
    return False


def _inspect_tools() -> tuple[list[str], list[str]]:
    """Return (inspected tool names, violations)."""
    inspected: list[str] = []
    violations: list[str] = []
    for path in walked_files(_SRC_ROOT, minimum=80):
        rel = str(path.relative_to(_SRC_ROOT))
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            if not any(_is_tool_decorator(d) for d in node.decorator_list):
                continue
            inspected.append(f"{rel}::{node.name}")
            if _returns_str(node.returns):
                violations.append(
                    f"{rel}:{node.lineno}: tool `{node.name}` returns `str` — return a dict or pydantic model so MCP clients can introspect"
                )
    return inspected, violations


def test_no_tool_returns_str() -> None:
    _, violations = _inspect_tools()
    assert not violations, "Tool returns bare `str`. CLAUDE.md ban — declare a typed response:\n  " + "\n  ".join(violations)


def test_the_matcher_still_matches_tools() -> None:
    """The guard for the guard — see the module docstring.

    If this fails, `test_no_tool_returns_str` is passing because it inspected
    nothing. Fix `_is_tool_decorator` to match however tools are registered
    now; do NOT lower `_MINIMUM_TOOLS` to make it green.
    """
    inspected, _ = _inspect_tools()
    assert len(inspected) >= _MINIMUM_TOOLS, (
        f"the tool matcher found {len(inspected)} tools (expected >= {_MINIMUM_TOOLS}): {inspected}.\n\n"
        "The return-type ban is therefore asserting nothing. This exact failure "
        "went unnoticed through the a2kit sunset because the test kept passing "
        "while matching a decorator that no longer existed."
    )
