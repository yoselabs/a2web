"""Architectural invariant: a2web has one logging channel — the a2kit-managed
`a2kit` logger — and no bare `structlog` emit channel.

a2web previously logged operational diagnostics through unconfigured
`structlog.get_logger("a2web…")` loggers, which (running on structlog defaults)
wrote to **stdout** — a JSON-RPC corruption hazard in MCP stdio mode — and
ignored `LogConfig` entirely. All such sites now route through the `a2kit`
logger (async via `a2kit.log.*`, sync via the `a2web.log` helper / stdlib).
This rule fails CI if a `structlog` logger is reintroduced under `src/a2web/`.

Companion to `test_no_ldd_terminology`.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "a2web"


def _imports_structlog(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "structlog" or alias.name.startswith("structlog.") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "structlog" or (node.module or "").startswith("structlog."):
                return True
    return False


def test_no_structlog_under_src() -> None:
    violations: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        rel = str(path.relative_to(_SRC_ROOT))
        source = path.read_text()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        if _imports_structlog(tree):
            violations.append(f"{rel}: imports `structlog` — use the a2kit-managed channel instead")
        if "structlog.get_logger" in source:
            violations.append(f"{rel}: references `structlog.get_logger` — the rogue logging channel is retired")

    assert not violations, (
        "Bare structlog logging reintroduced under src/a2web/ — emit through the "
        "`a2kit` logger (async: `a2kit.log.*`; sync: `a2web.log` helper):\n  " + "\n  ".join(violations)
    )
