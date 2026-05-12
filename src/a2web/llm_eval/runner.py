"""EvalSuite — matrix runner over (corpus x systems x judge).

For each `(entry, system)` cell:
  1. system.fetch(url, ask=entry.task) → SystemResult (answer + cost + metadata).
  2. judge.score(task, criteria, answer) → JudgeVerdict (scores + reached).
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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from ..packages.llm_extract import Judge, JudgeParseError, JudgeVerdict
from .corpus import Corpus, CorpusEntry
from .systems import EvalSystem, SystemResult

_LOG = structlog.get_logger("a2web.llm.eval")


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
    # Judge outcome (None if judge failed)
    judge_scores: list[int] | None
    judge_overall: int | None
    judge_reached: bool | None
    judge_reasoning: str | None
    judge_cost_usd: float = 0.0
    judge_latency_ms: int = 0
    judge_error: str | None = None


@dataclass(slots=True)
class EvalReport:
    """Aggregate outcome of a full suite run."""

    corpus_path: str
    output_dir: Path
    started_at: datetime
    ended_at: datetime
    systems: list[str]
    judge_model: str
    rows: list[EvalRow] = field(default_factory=list)

    @property
    def wall_seconds(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()


class EvalSuite:
    """Driver — pairs every corpus entry with every system, judges the answer.

    Stateless beyond construction; safe to construct once per run.
    """

    def __init__(
        self,
        *,
        corpus: Corpus,
        systems: list[EvalSystem],
        judge: Judge,
        concurrency: int = 4,
        output_dir: Path | str | None = None,
    ) -> None:
        if not systems:
            raise ValueError("EvalSuite requires at least one system")
        self._corpus = corpus
        self._systems = systems
        self._judge = judge
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
        rows: list[EvalRow] = []
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

        # 1) Fetch
        t0 = time.perf_counter()
        try:
            fetch_result: SystemResult = await system.fetch(url=entry.url, ask=entry.task)
        except Exception as exc:
            _LOG.warning(
                "eval_system_failed",
                slug=slug,
                system=system.name,
                error=str(exc),
            )
            fetch_latency_ms = int((time.perf_counter() - t0) * 1000)
            row = EvalRow(
                slug=slug,
                url=entry.url,
                url_class=entry.url_class,
                task=entry.task,
                system=system.name,
                answer="",
                fetch_latency_ms=fetch_latency_ms,
                fetch_cost_usd=0.0,
                fetch_prompt_tokens=0,
                fetch_completion_tokens=0,
                fetch_error=f"system_raised: {exc}",
                fetch_metadata={},
                judge_scores=None,
                judge_overall=None,
                judge_reached=None,
                judge_reasoning=None,
                judge_error="skipped_due_to_fetch_error",
            )
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

        # 2) Judge — skip if the system returned no answer (judging an empty
        # string just gives noisy 0s; mark as not-reached and move on).
        if not fetch_result.answer:
            row = EvalRow(
                slug=slug,
                url=entry.url,
                url_class=entry.url_class,
                task=entry.task,
                system=system.name,
                answer="",
                fetch_latency_ms=fetch_result.latency_ms,
                fetch_cost_usd=fetch_result.cost_usd,
                fetch_prompt_tokens=fetch_result.prompt_tokens,
                fetch_completion_tokens=fetch_result.completion_tokens,
                fetch_error=fetch_result.error,
                fetch_metadata=fetch_result.metadata,
                judge_scores=[0] * len(entry.criteria),
                judge_overall=0,
                judge_reached=False,
                judge_reasoning="empty answer from system",
            )
            (cell_dir / "row.json").write_text(_row_to_json(row))
            return row

        try:
            verdict: JudgeVerdict = await self._judge.score(
                task=entry.task,
                criteria=entry.criteria,
                answer=fetch_result.answer,
            )
        except JudgeParseError as exc:
            (cell_dir / "judge_raw.txt").write_text(exc.raw_text)
            row = EvalRow(
                slug=slug,
                url=entry.url,
                url_class=entry.url_class,
                task=entry.task,
                system=system.name,
                answer=fetch_result.answer,
                fetch_latency_ms=fetch_result.latency_ms,
                fetch_cost_usd=fetch_result.cost_usd,
                fetch_prompt_tokens=fetch_result.prompt_tokens,
                fetch_completion_tokens=fetch_result.completion_tokens,
                fetch_error=fetch_result.error,
                fetch_metadata=fetch_result.metadata,
                judge_scores=None,
                judge_overall=None,
                judge_reached=None,
                judge_reasoning=None,
                judge_error=f"parse_error: {exc}",
            )
            (cell_dir / "row.json").write_text(_row_to_json(row))
            return row

        row = EvalRow(
            slug=slug,
            url=entry.url,
            url_class=entry.url_class,
            task=entry.task,
            system=system.name,
            answer=fetch_result.answer,
            fetch_latency_ms=fetch_result.latency_ms,
            fetch_cost_usd=fetch_result.cost_usd,
            fetch_prompt_tokens=fetch_result.prompt_tokens,
            fetch_completion_tokens=fetch_result.completion_tokens,
            fetch_error=fetch_result.error,
            fetch_metadata=fetch_result.metadata,
            judge_scores=verdict.scores,
            judge_overall=verdict.overall,
            judge_reached=verdict.reached,
            judge_reasoning=verdict.reasoning,
            judge_cost_usd=verdict.cost_usd,
            judge_latency_ms=verdict.latency_ms,
        )
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
            "fetch_metadata": row.fetch_metadata,
            "judge_scores": row.judge_scores,
            "judge_overall": row.judge_overall,
            "judge_reached": row.judge_reached,
            "judge_reasoning": row.judge_reasoning,
            "judge_cost_usd": row.judge_cost_usd,
            "judge_latency_ms": row.judge_latency_ms,
            "judge_error": row.judge_error,
        },
        indent=2,
        default=str,
    )


__all__ = ["EvalReport", "EvalRow", "EvalSuite"]
