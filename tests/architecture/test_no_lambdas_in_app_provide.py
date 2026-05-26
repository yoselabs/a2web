"""Architectural invariant: `app.provide(...)` accepts a named callable,
not a lambda.

a2kit v0.36+ rejects lambdas at registration time (no return annotation),
but the rejection happens at import time of `server.py` only — easy to miss
during testing. This rule fails CI on the first commit that introduces one.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "a2web"


def _is_app_provide(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "provide":
        # Heuristic: receiver is a Name "app" or "self.app" etc.
        # We don't need to be strict here — the only `.provide(...)` calls in
        # a2web are on a2kit App instances, and the false-positive surface is
        # negligible.
        return True
    return False


def test_no_lambdas_in_app_provide() -> None:
    violations: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        rel = str(path.relative_to(_SRC_ROOT))
        source = path.read_text()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_app_provide(node):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Lambda):
                    violations.append(
                        f"{rel}:{arg.lineno}: lambda passed to `app.provide(...)` "
                        f"— a2kit v0.36+ rejects this. Define a named factory function "
                        f"with a return annotation."
                    )

    assert not violations, (
        "Lambda passed to `app.provide(...)` — rejected by a2kit:\n  "
        + "\n  ".join(violations)
    )
