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
from typing import Literal

from .._manifests.eval_systems import EvalSystemContext
from .._plugin import load_surface
from ..packages.llm_extract import Judge, LLMNotAvailable, ModelSpec, Provider
from ..settings import AppSettings
from ..state import bootstrap_state
from .bench_judge import BenchJudge
from .corpus import CorpusError, load_corpus
from .live_sink import LiveSink
from .report import stats_dict, write_all
from .runner import EvalSuite
from .systems import EvalSystem

_DEFAULT_CORPUS = Path("eval/corpus.yaml")
_PROVIDER_ENV = "A2WEB_BENCH_PROVIDER"


_BENCH_PROVIDER_IDS = ("claude-code", "anthropic")


def _pick_provider(
    settings: AppSettings,
) -> tuple[Provider, Literal["anthropic", "claude-code"]]:
    """Select the benchmark LLM provider via the plugin manifest registry.

    Prefers `claude-code` (OAuth subscription — no API key) and falls back
    to `anthropic`. `A2WEB_BENCH_PROVIDER` forces the choice; an explicit
    override that isn't in the registry raises `LLMNotAvailable`.
    """
    registry = load_surface("a2web._manifests.llm_providers", Provider, settings)
    override = os.environ.get(_PROVIDER_ENV, "").strip().lower().replace("_", "-")
    if override:
        if override not in _BENCH_PROVIDER_IDS:
            raise LLMNotAvailable(f"unknown provider id: {override}")
        provider = registry.get(override)
        if provider is None:
            raise LLMNotAvailable(f"{_PROVIDER_ENV}={override} but provider not in registry (available: {sorted(registry)})")
        # Narrow the literal — checked above.
        if override == "anthropic":
            return provider, "anthropic"
        return provider, "claude-code"
    for name in _BENCH_PROVIDER_IDS:
        provider = registry.get(name)
        if provider is not None:
            if name == "anthropic":
                return provider, "anthropic"
            return provider, "claude-code"
    raise LLMNotAvailable(f"no LLM provider available (registry empty: {sorted(registry)})")


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

    # Bench uses a stand-in AppSettings; provider selection only reads
    # llm_api_key_env (default "ANTHROPIC_API_KEY") so AppSettings() suffices.
    settings_bootstrap = AppSettings()
    try:
        provider, provider_id = _pick_provider(settings_bootstrap)
    except LLMNotAvailable as exc:
        print(f"LLM provider unavailable: {exc}", file=sys.stderr)
        return 3

    # Thread the provider choice into A2WebExtract's reader path too — its
    # extractor builds its own provider from settings.
    settings = AppSettings(llm_provider=provider_id)
    # Single source of truth: bootstrap_state constructs both AppState and
    # the Resources bundle (browser_pool + llm_extractor + cookie_jar).
    # Closes the v0.22 bench-harness gap — adding a resource only needs to
    # extend bootstrap_state, no eval-side wiring drift.
    state, resources = await bootstrap_state(settings)

    # Eval systems load via the plugin manifest registry.
    # Mode controls which manifests we keep — the registry is built once;
    # we filter by name. Adding a new system = drop a manifest in
    # `_manifests/eval_systems/`; no edit required here.
    registry = load_surface(
        "a2web._manifests.eval_systems",
        EvalSystem,
        EvalSystemContext(provider=provider, state=state, resources=resources),
    )
    keep_by_mode: dict[str, tuple[str, ...]] = {
        "default": ("webfetch_baseline", "a2web_detail", "a2web_extract"),
        "baseline": ("webfetch_baseline",),
        "detail": ("a2web_detail", "a2web_extract"),
    }
    systems: list[EvalSystem] = [registry[name] for name in keep_by_mode[args.mode] if name in registry]

    judge_model = ModelSpec(provider_id, args.judge_model)
    judge = Judge(provider=provider, model=judge_model)
    bench_judge = BenchJudge(provider=provider, model=judge_model)

    output_dir = args.output_dir or Path("eval/runs") / datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")

    live_sink = LiveSink(total=len(corpus) * len(systems))
    suite = EvalSuite(
        corpus=corpus,
        systems=systems,
        judge=judge,
        bench_judge=bench_judge,
        concurrency=args.concurrency,
        output_dir=output_dir,
        handlers=(live_sink,),
    )

    print(f"Running benchmark: {len(corpus)} URLs x {len(systems)} systems (provider={provider_id}) → {output_dir}")
    # Lifecycle the browser pool around the run — Camoufox launches lazily on
    # first acquire, but `__aexit__` is what cleanly closes the browser process.
    async with resources.browser_pool, live_sink:
        report = await suite.run()
    write_all(report)
    print(json.dumps(stats_dict(report), indent=2, default=str))
    print(f"\nReport written to: {output_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    rc = asyncio.run(_amain(argv if argv is not None else sys.argv[1:]))
    # Hard-exit after the report is written. The bench is a one-shot CLI with
    # no graceful-shutdown contract: `write_all` is done and stdout is flushed
    # below, and `async with` already fired every `__aexit__`. A non-daemon
    # background thread (a curl_cffi / SDK worker parked on
    # `queue.SimpleQueue.get`) otherwise blocks `Py_FinalizeEx →
    # wait_for_thread_shutdown`, hanging the process after the stats dump and
    # forcing a manual SIGKILL. `os._exit` skips interpreter finalize — and
    # because the Python parent dies immediately, the lazily-launched Camoufox
    # subprocess reaps itself via its parent-death pipe instead of lingering.
    # See eval/findings_2026-05-26-shutdown-thread-leak-spike.md + the
    # `bench-shutdown-thread-leak` BACKLOG entry. Root-cause attribution
    # (which dep leaks the thread) stays open upstream.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)


if __name__ == "__main__":
    main()
