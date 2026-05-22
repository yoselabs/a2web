"""EvalSuite — matrix runner over (corpus x systems x judges).

For each `(entry, system)` cell:
  1. system.fetch(url, ask=entry.task) → SystemResult (answer + cost + metadata).
  2. Four axes are scored:
     - answer quality   — `Judge` against per-question criteria.
     - token cost       — tokens of the response envelope (from metadata).
     - data contract    — deterministic envelope field-presence check.
     - output clarity   — `BenchJudge.score_clarity`.
     plus `next_links_picked_correctly` on listing-style entries.
  3. Persist a trace dir under runs/<slug>/<system>/ for debugging.
  4. Append a flat row to results.tsv via the report writer.

Concurrency is bounded — too many parallel fetches knock over polite
sites and hammer the rate limit of every provider in the matrix. Default
4-way; configurable.

`run()` returns an `EvalReport` carrying the per-row records; the caller
writes the dated output dir via `report.write_all(...)`.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from a2kit.ldd import ldd_state_for_call
from a2kit.packages.testing.null_context import null_context

from ..packages.llm_extract import Judge, JudgeParseError, JudgeVerdict
from .bench_judge import BenchJudge
from .contract import check_envelope_contract
from .corpus import Corpus, CorpusEntry
from .systems import EvalSystem, SystemResult

_LOG = structlog.get_logger("a2web.llm.eval")


@contextmanager
def _ldd_ambient() -> Iterator[None]:
    """Establish a no-op LDD ambient for a direct `fetcher.fetch` call.

    The benchmark drives the a2web orchestrator outside any tool dispatch;
    a2kit v0.39 requires an ambient LDD context for the orchestrator's
    `a2kit.ldd.event(...)` calls. Events and reports are disabled — the
    benchmark measures the response envelope, not the LDD stream.
    """
    with ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False):
        yield


@dataclass(slots=True)
class EvalRow:
    """One row in the eval matrix — (entry, system) coordinates + outcomes."""

    slug: str
    url: str
    url_class: str
    task: str
    system: str
    # Fetch outcome
    answer: str
    fetch_latency_ms: int
    fetch_cost_usd: float
    fetch_prompt_tokens: int
    fetch_completion_tokens: int
    fetch_error: str | None
    fetch_metadata: dict[str, Any]
    # Axis 1 — answer quality (None if judge failed)
    judge_scores: list[int] | None
    judge_overall: int | None
    judge_reached: bool | None
    judge_reasoning: str | None
    judge_cost_usd: float = 0.0
    judge_latency_ms: int = 0
    judge_error: str | None = None
    # Axis 2 — token cost of the response envelope the agent reads
    envelope_tokens_total: int = 0
    envelope_tokens_by_field: dict[str, int] = field(default_factory=dict)
    # Axis 3 — data-contract conformance (None = not applicable, e.g. WebFetch)
    contract_conformant: bool | None = None
    contract_violations: list[str] = field(default_factory=list)
    contract_conformant_debug: bool | None = None
    contract_violations_debug: list[str] = field(default_factory=list)
    # Axis 4 — output clarity (None if not scored)
    clarity_score: int | None = None
    clarity_reasoning: str | None = None
    clarity_error: str | None = None
    # next_links_picked_correctly — listing entries only
    next_links_score: int | None = None
    next_links_reasoning: str | None = None
    next_links_error: str | None = None


@dataclass(slots=True)
class EvalReport:
    """Aggregate outcome of a full suite run."""

    corpus_path: str
    output_dir: Path
    started_at: datetime
    ended_at: datetime
    systems: list[str]
    judge_model: str
    bench_judge_model: str | None = None
    rows: list[EvalRow] = field(default_factory=list)

    @property
    def wall_seconds(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()


class EvalSuite:
    """Driver — pairs every corpus entry with every system, scores four axes.

    Stateless beyond construction; safe to construct once per run.
    """

    def __init__(
        self,
        *,
        corpus: Corpus,
        systems: list[EvalSystem],
        judge: Judge,
        bench_judge: BenchJudge | None = None,
        concurrency: int = 4,
        output_dir: Path | str | None = None,
    ) -> None:
        if not systems:
            raise ValueError("EvalSuite requires at least one system")
        self._corpus = corpus
        self._systems = systems
        self._judge = judge
        self._bench_judge = bench_judge
        self._concurrency = max(1, concurrency)
        if output_dir is None:
            output_dir = Path("eval/runs") / datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        self._output_dir = Path(output_dir)

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    async def run(self) -> EvalReport:
        """Execute the matrix. Returns the report; caller persists via
        report.write_all() if a dated output dir is desired."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        traces_root = self._output_dir / "trace"
        traces_root.mkdir(parents=True, exist_ok=True)

        started_at = datetime.now(UTC)
        sem = asyncio.Semaphore(self._concurrency)

        async def _process_cell(entry: CorpusEntry, system: EvalSystem) -> EvalRow:
            async with sem:
                return await self._run_one(entry, system, traces_root)

        # Build the full task list (corpus x systems) and run with bounded
        # concurrency. Ordering of rows is corpus-major / system-minor.
        tasks: list[asyncio.Task[EvalRow]] = []
        for entry in self._corpus.entries:
            for system in self._systems:
                tasks.append(asyncio.create_task(_process_cell(entry, system)))

        rows = await asyncio.gather(*tasks)
        ended_at = datetime.now(UTC)

        return EvalReport(
            corpus_path=str(self._corpus.source_path),
            output_dir=self._output_dir,
            started_at=started_at,
            ended_at=ended_at,
            systems=[s.name for s in self._systems],
            judge_model=self._judge.model.model,
            bench_judge_model=self._bench_judge.model.model if self._bench_judge else None,
            rows=list(rows),
        )

    async def _run_one(
        self,
        entry: CorpusEntry,
        system: EvalSystem,
        traces_root: Path,
    ) -> EvalRow:
        slug = entry.slug
        cell_dir = traces_root / slug / system.name
        cell_dir.mkdir(parents=True, exist_ok=True)

        # 1) Fetch — under a no-op LDD ambient so the a2web orchestrator's
        # `a2kit.ldd.event(...)` calls resolve outside a tool dispatch.
        t0 = time.perf_counter()
        try:
            with _ldd_ambient():
                fetch_result: SystemResult = await system.fetch(url=entry.url, ask=entry.task)
        except Exception as exc:
            _LOG.warning("eval_system_failed", slug=slug, system=system.name, error=str(exc))
            fetch_latency_ms = int((time.perf_counter() - t0) * 1000)
            row = _base_row(entry, system.name, answer="")
            row.fetch_latency_ms = fetch_latency_ms
            row.fetch_error = f"system_raised: {exc}"
            row.judge_error = "skipped_due_to_fetch_error"
            (cell_dir / "row.json").write_text(_row_to_json(row))
            return row

        (cell_dir / "answer.txt").write_text(fetch_result.answer or "")
        (cell_dir / "fetch_result.json").write_text(
            json.dumps(
                {
                    "system": fetch_result.system,
                    "latency_ms": fetch_result.latency_ms,
                    "cost_usd": fetch_result.cost_usd,
                    "prompt_tokens": fetch_result.prompt_tokens,
                    "completion_tokens": fetch_result.completion_tokens,
                    "error": fetch_result.error,
                    "metadata": fetch_result.metadata,
                },
                indent=2,
                default=str,
            )
        )

        # 2) Token-cost + data-contract axes — deterministic, no LLM.
        row = _base_row(entry, system.name, answer=fetch_result.answer)
        row.fetch_latency_ms = fetch_result.latency_ms
        row.fetch_cost_usd = fetch_result.cost_usd
        row.fetch_prompt_tokens = fetch_result.prompt_tokens
        row.fetch_completion_tokens = fetch_result.completion_tokens
        row.fetch_error = fetch_result.error
        row.fetch_metadata = fetch_result.metadata
        _apply_token_axis(row, fetch_result)
        _apply_contract_axis(row, fetch_result, entry.url)

        # 3) No answer → judges skipped (judging an empty string is noise).
        if not fetch_result.answer:
            row.judge_scores = [0] * len(entry.criteria)
            row.judge_overall = 0
            row.judge_reached = False
            row.judge_reasoning = "empty answer from system"
            (cell_dir / "row.json").write_text(_row_to_json(row))
            return row

        # 4) Clarity + next_links axes — LLM-judged, run when a bench judge is
        # configured. Independent of the quality judge so one failing axis
        # does not sink the others.
        await self._score_clarity(row, entry, fetch_result)
        await self._score_next_links(row, entry, fetch_result, cell_dir)

        # 5) Answer-quality axis.
        try:
            verdict: JudgeVerdict = await self._judge.score(
                task=entry.task,
                criteria=entry.criteria,
                answer=fetch_result.answer,
            )
        except JudgeParseError as exc:
            (cell_dir / "judge_raw.txt").write_text(exc.raw_text)
            row.judge_error = f"parse_error: {exc}"
            (cell_dir / "row.json").write_text(_row_to_json(row))
            return row

        row.judge_scores = verdict.scores
        row.judge_overall = verdict.overall
        row.judge_reached = verdict.reached
        row.judge_reasoning = verdict.reasoning
        row.judge_cost_usd = verdict.cost_usd
        row.judge_latency_ms = verdict.latency_ms
        (cell_dir / "judge.json").write_text(
            json.dumps(
                {
                    "scores": verdict.scores,
                    "overall": verdict.overall,
                    "reached": verdict.reached,
                    "reasoning": verdict.reasoning,
                    "model": verdict.model,
                    "cost_usd": verdict.cost_usd,
                    "latency_ms": verdict.latency_ms,
                },
                indent=2,
                default=str,
            )
        )
        (cell_dir / "row.json").write_text(_row_to_json(row))
        return row

    async def _score_clarity(self, row: EvalRow, entry: CorpusEntry, fetch_result: SystemResult) -> None:
        """Output-clarity axis — graded for every system on every cell with a
        non-empty answer. No-op when no bench judge is configured."""
        if self._bench_judge is None:
            return
        try:
            verdict = await self._bench_judge.score_clarity(task=entry.task, answer=fetch_result.answer)
        except JudgeParseError as exc:
            _LOG.warning("clarity_judge_failed", slug=entry.slug, system=row.system, error=str(exc))
            row.clarity_error = f"parse_error: {exc}"
            return
        row.clarity_score = verdict.score
        row.clarity_reasoning = verdict.reasoning
        row.judge_cost_usd += verdict.cost_usd

    async def _score_next_links(
        self,
        row: EvalRow,
        entry: CorpusEntry,
        fetch_result: SystemResult,
        cell_dir: Path,
    ) -> None:
        """next_links_picked_correctly axis — graded only on listing entries
        for systems that actually produced a next_links block."""
        if self._bench_judge is None or not entry.next_links_expected:
            return
        block = _next_links_block(fetch_result)
        if block is None:
            return
        try:
            verdict = await self._bench_judge.score_next_links(task=entry.task, next_links=block)
        except JudgeParseError as exc:
            _LOG.warning("next_links_judge_failed", slug=entry.slug, system=row.system, error=str(exc))
            row.next_links_error = f"parse_error: {exc}"
            return
        row.next_links_score = verdict.score
        row.next_links_reasoning = verdict.reasoning
        row.judge_cost_usd += verdict.cost_usd
        (cell_dir / "next_links.json").write_text(
            json.dumps(
                {"score": verdict.score, "reasoning": verdict.reasoning, "block": block},
                indent=2,
                default=str,
            )
        )


def _base_row(entry: CorpusEntry, system: str, *, answer: str) -> EvalRow:
    """An EvalRow with coordinates set and every outcome at its empty default."""
    return EvalRow(
        slug=entry.slug,
        url=entry.url,
        url_class=entry.url_class,
        task=entry.task,
        system=system,
        answer=answer,
        fetch_latency_ms=0,
        fetch_cost_usd=0.0,
        fetch_prompt_tokens=0,
        fetch_completion_tokens=0,
        fetch_error=None,
        fetch_metadata={},
        judge_scores=None,
        judge_overall=None,
        judge_reached=None,
        judge_reasoning=None,
    )


def _apply_token_axis(row: EvalRow, fetch_result: SystemResult) -> None:
    """Read the envelope token breakdown the system recorded in metadata."""
    tokens = fetch_result.metadata.get("envelope_tokens")
    if isinstance(tokens, dict):
        total = tokens.get("total")
        per_field = tokens.get("per_field")
        row.envelope_tokens_total = int(total) if isinstance(total, int) else 0
        row.envelope_tokens_by_field = dict(per_field) if isinstance(per_field, dict) else {}


def _apply_contract_axis(row: EvalRow, fetch_result: SystemResult, requested_url: str) -> None:
    """Run the deterministic envelope contract check for both the debug=False
    and debug=True envelopes the system recorded. Systems without a structured
    envelope (WebFetch) leave the axis as None — not applicable."""
    envelope = fetch_result.metadata.get("envelope")
    if isinstance(envelope, dict):
        result = check_envelope_contract(envelope, requested_url=requested_url, debug=False)
        row.contract_conformant = result.conformant
        row.contract_violations = result.violations
    envelope_debug = fetch_result.metadata.get("envelope_debug")
    if isinstance(envelope_debug, dict):
        result_debug = check_envelope_contract(envelope_debug, requested_url=requested_url, debug=True)
        row.contract_conformant_debug = result_debug.conformant
        row.contract_violations_debug = result_debug.violations


def _next_links_block(fetch_result: SystemResult) -> str | None:
    """The rendered next_links block from the system's wire envelope, or None
    when the system produced no next_links."""
    envelope = fetch_result.metadata.get("envelope")
    if isinstance(envelope, dict):
        block = envelope.get("next_links")
        if isinstance(block, str) and block.strip():
            return block
    return None


def _row_to_json(row: EvalRow) -> str:
    return json.dumps(
        {
            "slug": row.slug,
            "url": row.url,
            "url_class": row.url_class,
            "task": row.task,
            "system": row.system,
            "fetch_latency_ms": row.fetch_latency_ms,
            "fetch_cost_usd": row.fetch_cost_usd,
            "fetch_prompt_tokens": row.fetch_prompt_tokens,
            "fetch_completion_tokens": row.fetch_completion_tokens,
            "fetch_error": row.fetch_error,
            "judge_scores": row.judge_scores,
            "judge_overall": row.judge_overall,
            "judge_reached": row.judge_reached,
            "judge_reasoning": row.judge_reasoning,
            "judge_cost_usd": row.judge_cost_usd,
            "judge_latency_ms": row.judge_latency_ms,
            "judge_error": row.judge_error,
            "envelope_tokens_total": row.envelope_tokens_total,
            "envelope_tokens_by_field": row.envelope_tokens_by_field,
            "contract_conformant": row.contract_conformant,
            "contract_violations": row.contract_violations,
            "contract_conformant_debug": row.contract_conformant_debug,
            "contract_violations_debug": row.contract_violations_debug,
            "clarity_score": row.clarity_score,
            "clarity_reasoning": row.clarity_reasoning,
            "clarity_error": row.clarity_error,
            "next_links_score": row.next_links_score,
            "next_links_reasoning": row.next_links_reasoning,
            "next_links_error": row.next_links_error,
        },
        indent=2,
        default=str,
    )


__all__ = ["EvalReport", "EvalRow", "EvalSuite"]
