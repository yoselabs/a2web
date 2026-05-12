"""CLI entry: `uv run python -m a2web.llm.eval`.

Three modes:
  default  — run the full matrix (WebFetchBaseline + A2WebDetail + A2WebExtract)
             against the given corpus, judge with Sonnet.
  baseline — only WebFetchBaseline; for drift-detection runs.
  detail   — only the two a2web systems; faster for engine-only checks.

Reads `ANTHROPIC_API_KEY` from the environment. Aborts with a clear message
if missing or if `[llm]` extras are not installed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from ..packages.llm_extract import Judge, LLMNotAvailable, ModelSpec
from ..packages.llm_extract.providers.anthropic import AnthropicProvider
from ..settings import AppSettings
from ..state import build_state
from .corpus import CorpusError, load_corpus
from .report import stats_dict, write_all
from .runner import EvalSuite
from .systems import A2WebDetail, A2WebExtract, EvalSystem, WebFetchBaseline

_DEFAULT_CORPUS = Path("benchmarks/vs-webfetch/2026-05-11/corpus.yaml")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="a2web.llm.eval")
    p.add_argument(
        "--corpus",
        type=Path,
        default=_DEFAULT_CORPUS,
        help=f"path to corpus.yaml (default: {_DEFAULT_CORPUS})",
    )
    p.add_argument(
        "--mode",
        choices=("default", "baseline", "detail"),
        default="default",
        help="which systems to include (default: all three)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="output directory (default: eval/runs/<timestamp>)",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="max in-flight (system x corpus) cells (default: 4)",
    )
    p.add_argument(
        "--judge-model",
        default="claude-sonnet-4-6",
        help="model id for the LLM judge (default: claude-sonnet-4-6)",
    )
    return p.parse_args(argv)


async def _amain(argv: list[str]) -> int:
    args = _parse_args(argv)

    try:
        corpus = load_corpus(args.corpus)
    except CorpusError as exc:
        print(f"corpus error: {exc}", file=sys.stderr)
        return 2

    try:
        provider = AnthropicProvider()
    except LLMNotAvailable as exc:
        print(f"LLM unavailable: {exc}", file=sys.stderr)
        return 3

    settings = AppSettings()
    state = build_state(settings)

    systems: list[EvalSystem] = []
    if args.mode in ("default", "baseline"):
        systems.append(WebFetchBaseline(provider=provider))
    if args.mode in ("default", "detail"):
        systems.append(A2WebDetail(state=state))
        systems.append(A2WebExtract(state=state))

    judge = Judge(provider=provider, model=ModelSpec("anthropic", args.judge_model))

    output_dir = args.output_dir or Path("eval/runs") / datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")

    suite = EvalSuite(
        corpus=corpus,
        systems=systems,
        judge=judge,
        concurrency=args.concurrency,
        output_dir=output_dir,
    )

    print(f"Running eval: {len(corpus)} URLs x {len(systems)} systems → {output_dir}")
    report = await suite.run()
    write_all(report)
    print(json.dumps(stats_dict(report), indent=2, default=str))
    print(f"\nReport written to: {output_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv if argv is not None else sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
