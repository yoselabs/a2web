"""CLI entry: `uv run python -m a2web.llm_eval` (`make bench` / `make eval`).

Runs the output benchmark — the (corpus x systems) matrix scored on four
axes (answer quality, token cost, output clarity, data-contract conformance)
plus the `next_links` axis on listing URLs.

Three modes:
  default  — full matrix (WebFetchBaseline + A2WebDetail + A2WebExtract).
  baseline — only WebFetchBaseline; for drift-detection runs.
  detail   — only the two a2web systems; faster for engine-only checks.

Provider: prefers Claude Code's OS session (OAuth subscription — no
`ANTHROPIC_API_KEY` needed), falls back to the Anthropic API provider.
`A2WEB_BENCH_PROVIDER` forces the choice (`claude-code` | `anthropic`).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from purgatory import AsyncCircuitBreakerFactory

from ..llm_resource import LlmExtractorResource
from ..packages.http_cache import SqliteResource
from ..packages.llm_extract import Judge, LLMNotAvailable, ModelSpec, Provider
from ..packages.llm_extract.providers.anthropic import AnthropicProvider
from ..packages.llm_extract.providers.claude_code import ClaudeCodeProvider
from ..packages.proxy_routing import ProxyEntryShape, ProxyPool, RouteRuleShape
from ..settings import AppSettings
from ..state import build_state
from .bench_judge import BenchJudge
from .corpus import CorpusError, load_corpus
from .report import stats_dict, write_all
from .runner import EvalSuite
from .systems import A2WebDetail, A2WebExtract, EvalSystem, WebFetchBaseline

_DEFAULT_CORPUS = Path("eval/corpus.yaml")
_PROVIDER_ENV = "A2WEB_BENCH_PROVIDER"


def _pick_provider() -> tuple[Provider, Literal["anthropic", "claude-code"]]:
    """Select the benchmark LLM provider.

    Prefers `ClaudeCodeProvider` (OAuth subscription — no API key) and falls
    back to `AnthropicProvider`. `A2WEB_BENCH_PROVIDER` forces the choice;
    an explicit `anthropic` override with no API key raises `LLMNotAvailable`.
    Returns the provider instance and its id (for `ModelSpec` / settings).
    """
    override = os.environ.get(_PROVIDER_ENV, "").strip().lower().replace("_", "-")
    if override == "anthropic":
        return AnthropicProvider(), "anthropic"
    if override == "claude-code":
        return ClaudeCodeProvider(), "claude-code"
    # Default: claude-code preferred, anthropic fallback.
    try:
        return ClaudeCodeProvider(), "claude-code"
    except LLMNotAvailable:
        return AnthropicProvider(), "anthropic"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="a2web.llm_eval")
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
        provider, provider_id = _pick_provider()
    except LLMNotAvailable as exc:
        print(f"LLM provider unavailable: {exc}", file=sys.stderr)
        return 3

    # Thread the provider choice into A2WebExtract's reader path too — its
    # extractor builds its own provider from settings.
    settings = AppSettings(llm_provider=provider_id)
    # Build the always-on state bundle directly — eval CLI bypasses the App
    # container; we construct the four resources here and inject the
    # extractor explicitly into A2WebExtract.
    sqlite = SqliteResource()
    state = build_state(
        settings=settings,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        proxy_pool=ProxyPool(
            routes=cast("list[RouteRuleShape]", settings.routes),
            proxies=cast("dict[str, ProxyEntryShape]", settings.proxies),
        ),
        sqlite=sqlite,
    )
    extractor = LlmExtractorResource(settings, sqlite)

    systems: list[EvalSystem] = []
    if args.mode in ("default", "baseline"):
        systems.append(WebFetchBaseline(provider=provider))
    if args.mode in ("default", "detail"):
        systems.append(A2WebDetail(state=state))
        systems.append(A2WebExtract(state=state, extractor=extractor))

    judge_model = ModelSpec(provider_id, args.judge_model)
    judge = Judge(provider=provider, model=judge_model)
    bench_judge = BenchJudge(provider=provider, model=judge_model)

    output_dir = args.output_dir or Path("eval/runs") / datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")

    suite = EvalSuite(
        corpus=corpus,
        systems=systems,
        judge=judge,
        bench_judge=bench_judge,
        concurrency=args.concurrency,
        output_dir=output_dir,
    )

    print(f"Running benchmark: {len(corpus)} URLs x {len(systems)} systems (provider={provider_id}) → {output_dir}")
    report = await suite.run()
    write_all(report)
    print(json.dumps(stats_dict(report), indent=2, default=str))
    print(f"\nReport written to: {output_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv if argv is not None else sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
