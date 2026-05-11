"""a2web.llm.eval — system adapters + matrix runner for benchmark evaluation.

`systems.py` exposes the `EvalSystem` Protocol plus the v0.4 adapters:
- `WebFetchBaseline` — faithful local reproduction of Claude Code's WebFetch.
- `A2WebDetail`     — a2web full envelope (current default response).
- `A2WebExtract`    — a2web with `ask=` (server-side extraction).

The matrix runner + corpus loader + report writer land in follow-up
commits (Step 6 — `make eval`).
"""

from __future__ import annotations

from .systems import (
    A2WebDetail,
    A2WebExtract,
    EvalSystem,
    SystemResult,
    WebFetchBaseline,
)

__all__ = [
    "A2WebDetail",
    "A2WebExtract",
    "EvalSystem",
    "SystemResult",
    "WebFetchBaseline",
]
