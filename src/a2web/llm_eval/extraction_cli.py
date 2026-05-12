"""CLI entry: `uv run python -m a2web.llm_eval.extraction_cli <corpus.yaml>`.

Runs the extraction-quality eval: fetches every URL in the corpus via
a2web (live pipeline, cache bypassed by default) and scores token-F1 +
length-ratio against the corpus `gold_md`. Emits JSON to stdout and
prints a one-line trip-decision verdict on stderr.

No LLM dependency. The Reader-LM v2 trip-condition is pure-Python.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from ..settings import AppSettings
from ..state import build_state
from .extraction import (
    ExtractionCorpusError,
    load_extraction_corpus,
    results_to_json,
    run_extraction_eval,
    summarize,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="a2web.llm_eval.extraction_cli")
    p.add_argument("corpus", type=Path, help="path to extraction-quality corpus.yaml")
    p.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="token-F1 threshold below which a URL counts as a 'miss' (default: 0.7)",
    )
    p.add_argument(
        "--miss-rate",
        type=float,
        default=0.10,
        help="miss-rate above which Reader-LM v2 trip is recommended (default: 0.10)",
    )
    p.add_argument(
        "--use-cache",
        action="store_true",
        help="use the local cache (default: bypass; we want the live pipeline)",
    )
    return p.parse_args(argv)


async def _amain(argv: list[str]) -> int:
    args = _parse_args(argv)
    try:
        corpus = load_extraction_corpus(args.corpus)
    except ExtractionCorpusError as exc:
        print(f"corpus error: {exc}", file=sys.stderr)
        return 2

    state = build_state(AppSettings())
    results = await run_extraction_eval(corpus, state, bypass_cache=not args.use_cache)
    summary = summarize(results, threshold=args.threshold, miss_rate=args.miss_rate)

    print(results_to_json(results, summary))

    verdict = "TRIP" if summary.trips_reader_lm_threshold else "OK"
    print(
        f"\n[{verdict}] n={summary.n} mean_f1={summary.mean_f1:.3f} "
        f"below_{args.threshold:.2f}={summary.below_07_count}/{summary.n} "
        f"({summary.below_07_pct:.1%}); Reader-LM v2 threshold "
        f"({args.miss_rate:.0%}) {'TRIPPED — recommend fallback' if summary.trips_reader_lm_threshold else 'not tripped'}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv if argv is not None else sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
