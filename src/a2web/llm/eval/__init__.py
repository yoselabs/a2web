"""a2web.llm.eval — system adapters + matrix runner for benchmark evaluation.

`systems.py` exposes the `EvalSystem` Protocol plus the v0.4 adapters:
- `WebFetchBaseline` — faithful local reproduction of Claude Code's WebFetch.
- `A2WebDetail`     — a2web full envelope (current default response).
- `A2WebExtract`    — a2web with `ask=` (server-side extraction).

The matrix runner + corpus loader + report writer land in follow-up
commits (Step 6 — `make eval`).
"""

from __future__ import annotations

from .corpus import Corpus, CorpusEntry, CorpusError, load_corpus
from .report import stats_dict, write_all
from .runner import EvalReport, EvalRow, EvalSuite
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
    "Corpus",
    "CorpusEntry",
    "CorpusError",
    "EvalReport",
    "EvalRow",
    "EvalSuite",
    "EvalSystem",
    "SystemResult",
    "WebFetchBaseline",
    "load_corpus",
    "stats_dict",
    "write_all",
]
