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

from anyllm import ProviderName, with_cost_guard
from plugin_surface import load_surface

from .._manifests.eval_systems import EvalSystemContext
from ..components import build_components
from ..llm_resource import _PROVIDER_ORDER, select_provider
from ..log import get_logger
from ..packages.llm_extract import Judge, LLMNotAvailable, ModelSpec, Provider
from ..settings import AppSettings
from .bench_judge import BenchJudge
from .corpus import Corpus, CorpusError, load_corpus
from .live_sink import LiveSink
from .report import stats_dict, write_all
from .runner import EvalSuite
from .systems import EvalSystem

_DEFAULT_CORPUS = Path("eval/corpus.yaml")
_PROVIDER_ENV = "A2WEB_BENCH_PROVIDER"


def _pick_provider(settings: AppSettings) -> tuple[Provider, str]:
    """Select the benchmark LLM provider via the shared `select_provider`.

    `A2WEB_BENCH_PROVIDER` forces the choice (validated against the known ids
    so a typo reads as "unknown provider id" rather than a generic miss);
    otherwise the shared auto-order applies. Raises `LLMNotAvailable` when
    nothing resolves.
    """
    raw = os.environ.get(_PROVIDER_ENV, "").strip().lower() or None
    override: ProviderName | None = None
    if raw is not None:
        try:
            override = ProviderName(raw)
        except ValueError:
            raise LLMNotAvailable(f"unknown provider id: {raw}") from None
    provider = select_provider(settings, override=override)
    if provider is None:
        target = str(override) if override is not None else f"auto ({', '.join(p.value for p in _PROVIDER_ORDER)})"
        raise LLMNotAvailable(f"no LLM provider available (tried: {target})")
    return provider, str(provider.name)


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
    p.add_argument(
        "--only",
        default=None,
        help="run only corpus cases of this class (e.g. 'listing') — a crucial subset to save quota",
    )
    p.add_argument(
        "--slug",
        action="append",
        default=None,
        metavar="SLUG",
        help="run only these corpus item(s) by slug (repeatable) — the finest isolation, one URL at a time",
    )
    p.add_argument(
        "--axis",
        action="append",
        default=None,
        choices=("quality", "clarity", "next_links"),
        help="run only these LLM-judged axes (repeatable); default all. The deterministic "
        "token + contract axes always run (they are free). Restricting axes cuts LLM-call count for spikes.",
    )
    return p.parse_args(argv)


async def _amain(argv: list[str]) -> int:
    args = _parse_args(argv)

    try:
        corpus = load_corpus(args.corpus)
    except CorpusError as exc:
        print(f"corpus error: {exc}", file=sys.stderr)
        return 2

    # --only <class>: run a crucial subset without editing the corpus. An empty
    # match fails loudly so a 0-cell run is never mistaken for a pass.
    if args.only is not None:
        matching = [e for e in corpus.entries if e.url_class == args.only]
        if not matching:
            known = ", ".join(sorted({e.url_class for e in corpus.entries if e.url_class}))
            print(f"0 cases match class {args.only!r} (known: {known})", file=sys.stderr)
            return 2
        corpus = Corpus(entries=matching, source_path=corpus.source_path)

    # --slug <id> [...]: single-item isolation (finer than --only <class>). Empty
    # match fails loud so a 0-cell run is never mistaken for a pass.
    if args.slug:
        wanted = set(args.slug)
        matching = [e for e in corpus.entries if e.slug in wanted]
        if not matching:
            known = ", ".join(sorted(e.slug for e in corpus.entries))
            print(f"0 cases match slug(s) {sorted(wanted)} (known: {known})", file=sys.stderr)
            return 2
        corpus = Corpus(entries=matching, source_path=corpus.source_path)

    # Bench uses a stand-in AppSettings; provider selection only reads
    # llm_api_key_env (default "ANTHROPIC_API_KEY") so AppSettings() suffices.
    settings = AppSettings()
    try:
        provider, provider_id = _pick_provider(settings)
    except LLMNotAvailable as exc:
        print(f"LLM provider unavailable: {exc}", file=sys.stderr)
        return 3

    # Cost guard (ADR-0016): wrap the provider so every `complete()` asserts the
    # (provider.name, model) pair BEFORE the network call. Wrapping here — the one
    # place the provider is acquired — means the runner, the judges, and the
    # extraction resource all receive the guarded provider; no un-guarded
    # completion path exists. A denied pair (e.g. anthropic-api:sonnet, the $20
    # case) raises CostViolation before spending, never silently bills. The shelf
    # guard keys on the anyllm ProviderName (`provider.name`), so no separate id
    # is passed; `provider_id` stays a2web's manifest alias for provenance below.
    provider = with_cost_guard(provider)

    # Single source of truth (sunset Phase 4): `build_components` is the ONE
    # composition root — the bench builds the same graph production does, so a
    # resource added there cannot miss the bench. The chosen provider is
    # injected as the provider factory, so the A2WebExtract reader path uses
    # the same backend as the judges — no `settings.llm_provider` round-trip.
    def _bench_provider(_settings: AppSettings) -> Provider:
        return provider

    resources = build_components(settings=settings, provider_factory=_bench_provider)
    state = await resources.state()

    # Eval systems load via the plugin manifest registry.
    # Mode controls which manifests we keep — the registry is built once;
    # we filter by name. Adding a new system = drop a manifest in
    # `_manifests/eval_systems/`; no edit required here.
    registry = load_surface(
        "a2web._manifests.eval_systems",
        EvalSystem,
        EvalSystemContext(provider=provider, state=state, resources=resources),
        logger=get_logger(),
    )
    keep_by_mode: dict[str, tuple[str, ...]] = {
        "default": ("webfetch_baseline", "a2web_detail", "a2web_extract"),
        "baseline": ("webfetch_baseline",),
        "detail": ("a2web_detail", "a2web_extract"),
    }
    systems: list[EvalSystem] = [registry[name] for name in keep_by_mode[args.mode] if name in registry]

    judge_model = ModelSpec(args.judge_model)
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
        provider=provider_id,
        axes=frozenset(args.axis) if args.axis else None,
    )

    print(f"Running benchmark: {len(corpus)} URLs x {len(systems)} systems (provider={provider_id}) → {output_dir}")
    # The engine launches lazily on first render; `ResourceScope.aclose()` is
    # what cleanly closes the browser process (and everything else the run
    # entered), LIFO, whether or not the run raised.
    try:
        async with live_sink:
            report = await suite.run()
    finally:
        await resources.aclose()
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
