"""a2web.llm_eval — the output benchmark: system adapters + matrix runner.

`systems.py` exposes the `EvalSystem` Protocol plus the adapters:
- `WebFetchBaseline` — faithful local reproduction of Claude Code's WebFetch.
- `A2WebDetail`     — a2web full envelope (current default response).
- `A2WebExtract`    — a2web with `ask=` (server-side extraction).

`runner.py` runs the (corpus x systems) matrix and scores four axes per
cell: answer quality, token cost, output clarity, data-contract conformance
(plus `next_links` quality on listing URLs). `make bench` / `make eval`
drive it via `__main__.py`.
"""

from __future__ import annotations

from .bench_judge import BenchJudge, ClarityVerdict, NextLinksVerdict
from .contract import ContractResult, check_envelope_contract
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
from .tokens import EnvelopeTokens, envelope_token_breakdown, estimate_tokens

__all__ = [
    "A2WebDetail",
    "A2WebExtract",
    "BenchJudge",
    "ClarityVerdict",
    "ContractResult",
    "Corpus",
    "CorpusEntry",
    "CorpusError",
    "EnvelopeTokens",
    "EvalReport",
    "EvalRow",
    "EvalSuite",
    "EvalSystem",
    "NextLinksVerdict",
    "SystemResult",
    "WebFetchBaseline",
    "check_envelope_contract",
    "envelope_token_breakdown",
    "estimate_tokens",
    "load_corpus",
    "stats_dict",
    "write_all",
]
