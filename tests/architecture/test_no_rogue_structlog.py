"""Architectural invariant: a2web has one logging channel — the `a2web` logger
— and no bare `structlog` emit channel.

a2web previously logged operational diagnostics through unconfigured
`structlog.get_logger("a2web…")` loggers, which (running on structlog defaults)
wrote to **stdout** — a JSON-RPC corruption hazard in MCP stdio mode — and
ignored `LogConfig` entirely. All such sites now route through the `a2web`
logger (async via `a2web.log.*`, sync via the `log_debug`/`log_info`/… helpers).

**The hazard did not leave with a2kit; it got closer.** a2web now owns the
logging setup itself (`server._configure_logging`), so `propagate=False` plus
the NullHandler floor is a2web's own invariant to keep rather than a framework
guarantee it inherits. A record that escapes to the root logger's default
stderr writer can still interleave with the JSON-RPC stream, and `structlog`'s
default configuration writes to stdout, which is worse.

This rule fails CI if a `structlog` logger is reintroduced under `src/a2web/`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._walk import walked_files

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
    for path in walked_files(_SRC_ROOT, minimum=80):
        rel = str(path.relative_to(_SRC_ROOT))
        source = path.read_text()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        if _imports_structlog(tree):
            violations.append(f"{rel}: imports `structlog` — use the `a2web` logging channel instead")
        if "structlog.get_logger" in source:
            violations.append(f"{rel}: references `structlog.get_logger` — the rogue logging channel is retired")

    assert not violations, (
        "Bare structlog logging reintroduced under src/a2web/ — emit through the "
        "`a2web` logger (async: `await a2web.log.*`; sync: the `log_*` helpers):\n  " + "\n  ".join(violations)
    )
