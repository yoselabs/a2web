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
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .. import log as a2web_log
from ..packages.llm_extract import Judge, JudgeParseError, JudgeVerdict
from .bench_judge import BenchJudge
from .case_contract import CONTRACT_KEYS, REPLAY_ONLY_KEYS, check_contract_keys
from .contract import check_envelope_contract
from .corpus import Corpus, CorpusEntry
from .events import CellEnded, CellStarted, FailureReason
from .systems import EvalSystem, SystemResult


@contextmanager
def _log_ambient(handlers: tuple[logging.Handler, ...] = ()) -> Iterator[None]:
    """Attach bench handlers to the `a2web` logger for the matrix run.

    `await a2web_log.info(...)` logs unconditionally to
    `logging.getLogger("a2web")` — no ambient ctx or call scope is required.
    To surface bench-cell signals (`CellStarted` / `CellEnded`) on a
    `LiveSink`, attach it as a handler for the run duration; this is exactly
    what `app.log.add_handler` does (`logging.getLogger("a2web").addHandler`).

    The a2web orchestrator's `StageStarted`/`StageEnded` events flow to the
    same handlers, but the bench handlers filter by event name and ignore
    them.

    The bench runs without an `App`, so a2kit's `_log_bootstrap` (which sets
    `a2kit.setLevel(DEBUG)`) never fires — the logger would default to the
    root's WARNING and gate our INFO events. We set it to INFO for the run
    duration and restore the prior level on exit.
    """
    a2web_logger = logging.getLogger("a2web")
    prior_level = a2web_logger.level
    a2web_logger.setLevel(logging.INFO)
    for handler in handlers:
        a2web_logger.addHandler(handler)
    try:
        yield
    finally:
        for handler in handlers:
            a2web_logger.removeHandler(handler)
        a2web_logger.setLevel(prior_level)


class AxisDisposition(StrEnum):
    """Why an axis does or does not carry a score for one cell.

    A bare `score: int | None` cannot express this, and the ambiguity was not
    theoretical: `EvalRow` used to document two different meanings for the same
    `None` three lines apart ("not applicable, e.g. WebFetch" on the contract
    axis, "not scored" on clarity), while `next_links` silently carried a third
    — *the harness read a field the envelope no longer has*. That third meaning
    is what let the next_links axis score zero cells for five weeks.
    """

    SCORED = "scored"
    #: The corpus entry does not ask for this axis, or the system cannot serve
    #: it (WebFetch has no structured envelope to check a contract against).
    #: Excluded from the axis denominator.
    NOT_APPLICABLE = "not_applicable"
    #: The axis was asked for and produced nothing. Counts toward the
    #: denominator as an unscored cell and always carries a `reason`.
    UNSCORED = "unscored"


@dataclass(slots=True)
class ScoreAxis:
    """An LLM-judged 0-5 axis — clarity, next_links."""

    disposition: AxisDisposition = AxisDisposition.NOT_APPLICABLE
    score: int | None = None
    reasoning: str | None = None
    reason: str | None = None

    def mark_unscored(self, reason: str) -> None:
        self.disposition = AxisDisposition.UNSCORED
        self.reason = reason

    def mark_scored(self, *, score: int, reasoning: str | None) -> None:
        self.disposition = AxisDisposition.SCORED
        self.score = score
        self.reasoning = reasoning


@dataclass(slots=True)
class QualityAxis:
    """Answer quality — the per-criterion judge."""

    disposition: AxisDisposition = AxisDisposition.NOT_APPLICABLE
    scores: list[int] | None = None
    overall: int | None = None
    reached: bool | None = None
    reasoning: str | None = None
    reason: str | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass(slots=True)
class ContractAxis:
    """Deterministic envelope field-presence conformance."""

    disposition: AxisDisposition = AxisDisposition.NOT_APPLICABLE
    conformant: bool | None = None
    violations: list[str] = field(default_factory=list)
    reason: str | None = None


@dataclass(slots=True)
class TokenAxis:
    """Token cost of the envelope the agent reads. Deterministic and free."""

    disposition: AxisDisposition = AxisDisposition.NOT_APPLICABLE
    total: int = 0
    by_field: dict[str, int] = field(default_factory=dict)
    reason: str | None = None


@dataclass(slots=True)
class EvalRow:
    """One row in the eval matrix — (entry, system) coordinates + outcomes.

    Every axis is a record carrying its own disposition. There is no bare
    nullable score on this model on purpose: an absent score cannot say whether
    the system correctly produced nothing or the harness failed to read what it
    produced, and those two were indistinguishable for the entire life of the
    next_links axis.
    """

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
    # The five axes.
    quality: QualityAxis = field(default_factory=QualityAxis)
    tokens: TokenAxis = field(default_factory=TokenAxis)
    contract: ContractAxis = field(default_factory=ContractAxis)
    contract_debug: ContractAxis = field(default_factory=ContractAxis)
    case_contract: ContractAxis = field(default_factory=ContractAxis)
    clarity: ScoreAxis = field(default_factory=ScoreAxis)
    next_links: ScoreAxis = field(default_factory=ScoreAxis)
    # Provenance (ADR-0016) — which provider actually served this cell's calls.
    provider: str = "unknown"

    def axis(self, name: str) -> ScoreAxis | QualityAxis | ContractAxis | TokenAxis:
        """The axis record by report name. Raises on an unknown axis rather
        than returning a default, so a renamed axis fails loudly."""
        return getattr(self, _AXIS_ATTR[name])


#: Report axis name -> `EvalRow` attribute. Literal, like `wire._TSV_FIELDS`:
#: which axes exist is a contract, and deriving it from model introspection is
#: how an axis silently changes shape.
_AXIS_ATTR = {
    "quality": "quality",
    "tokens": "tokens",
    "contract": "contract",
    "contract_debug": "contract_debug",
    "case_contract": "case_contract",
    "clarity": "clarity",
    "next_links": "next_links",
}

#: Axes whose absence means the harness is broken rather than the run being
#: uninteresting. The deterministic axes (tokens, contract) are excluded: a
#: WebFetch-only run legitimately scores neither.
_JUDGED_AXES = ("quality", "clarity", "next_links")

#: The fraction of its REQUESTED cells a judged axis must score, PER SYSTEM, for
#: the run to be usable. Declared, not implicit — a floor nobody can name is a
#: floor nobody can argue with.
#:
#: Per system, not per run, because the denominator that matters is the one the
#: comparison is drawn across: a run whose axis is 128/132 overall looks healthy
#: while one system silently contributed most of the loss.
#:
#: **0.90 would NOT have caught 2026-08-02, and saying so is the point.** That
#: run lost 4 of 132 quality cells; the worst system was 41/44, which is 93% —
#: above this floor by design, because ~3% judge wobble is currently normal and
#: a gate that fires on every run is a gate that gets ignored. What made that
#: run untrustworthy was not the SIZE of the loss but its CORRELATION: three of
#: four losses hit one system, on a comparison whose headline gap was 0.03. That
#: needs a skew test against the other systems' coverage, not a floor, and it is
#: recorded as open in `BACKLOG.md` rather than claimed here.
#:
#: So this catches the degradation the spec names — an axis quietly narrowing
#: run over run — and does not catch the correlated loss. Both are real; only
#: one is closed.
AXIS_COVERAGE_FLOOR = 0.90


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
    # Provenance (ADR-0016) — the provider id that served this run's LLM calls
    # (e.g. `claude-code` subscription vs metered `anthropic`). A run that hit
    # the metered API is identifiable from its own artifact.
    provider: str = "unknown"
    #: Whether the extraction cache was bypassed. A run that does not state
    #: this cannot be read as evidence of reproduction: repeat cells served
    #: from cache are one observation reported N times.
    extraction_cache_bypassed: bool = False
    rows: list[EvalRow] = field(default_factory=list)

    @property
    def wall_seconds(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()

    def axis_coverage(self, name: str) -> AxisCoverage:
        """How many cells this axis scored, skipped, and failed to score."""
        dispositions = [self.axis_of(row, name).disposition for row in self.rows]
        return AxisCoverage(
            axis=name,
            scored=sum(1 for d in dispositions if d is AxisDisposition.SCORED),
            not_applicable=sum(1 for d in dispositions if d is AxisDisposition.NOT_APPLICABLE),
            unscored=sum(1 for d in dispositions if d is AxisDisposition.UNSCORED),
        )

    @staticmethod
    def axis_of(row: EvalRow, name: str) -> ScoreAxis | QualityAxis | ContractAxis | TokenAxis:
        return row.axis(name)

    def broken_axes(self) -> tuple[str, ...]:
        """Judged axes that were requested on ≥1 cell and scored on none.

        Zero scores where at least one cell asked for a score is a broken
        harness, not a result — the state the next_links axis sat in for five
        weeks while the report rendered the same dash it uses for an axis the
        corpus never asked for.
        """
        broken = []
        for name in _JUDGED_AXES:
            coverage = self.axis_coverage(name)
            if coverage.requested and coverage.scored == 0:
                broken.append(name)
        return tuple(broken)

    def thin_axes(self) -> tuple[tuple[str, str, int, int], ...]:
        """`(axis, system, scored, requested)` for every axis/system pair that
        scored SOME cells but fewer than `AXIS_COVERAGE_FLOOR` of them.

        The gap `broken_axes` leaves. Failing only at ZERO coverage means an
        axis can degrade from full coverage to a handful of cells across runs
        while every run exits 0 — the honest denominator is reported, but a
        report is not a gate: it needs a human to notice a number that shrank,
        run over run, in a table under a leaderboard.

        Split per system for the reason the denominator exists at all: the
        numbers above it are compared ACROSS systems, so an axis at 128/132
        overall can hide one system carrying most of the loss.

        See `AXIS_COVERAGE_FLOOR` for what this deliberately does NOT catch.
        """
        thin: list[tuple[str, str, int, int]] = []
        for name in _JUDGED_AXES:
            for system in sorted({row.system for row in self.rows}):
                rows = [r for r in self.rows if r.system == system]
                scored = sum(1 for r in rows if r.axis(name).disposition is AxisDisposition.SCORED)
                unscored = sum(1 for r in rows if r.axis(name).disposition is AxisDisposition.UNSCORED)
                requested = scored + unscored
                if not requested or scored == 0:
                    continue  # zero coverage is `broken_axes`' call, not this one
                if scored < requested * AXIS_COVERAGE_FLOOR:
                    thin.append((name, system, scored, requested))
        return tuple(thin)


@dataclass(slots=True, frozen=True)
class AxisCoverage:
    """The denominator of one axis. Every reported statistic carries one."""

    axis: str
    scored: int
    not_applicable: int
    unscored: int

    @property
    def requested(self) -> int:
        """Cells that asked for this axis, whether or not they got a score."""
        return self.scored + self.unscored


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
        handlers: tuple[logging.Handler, ...] = (),
        provider: str = "unknown",
        axes: frozenset[str] | None = None,
        extraction_cache_bypassed: bool = False,
    ) -> None:
        if not systems:
            raise ValueError("EvalSuite requires at least one system")
        self._corpus = corpus
        self._systems = systems
        self._judge = judge
        self._bench_judge = bench_judge
        self._concurrency = max(1, concurrency)
        self._handlers = handlers
        self._provider = provider
        self._extraction_cache_bypassed = extraction_cache_bypassed
        # Which LLM-judged axes to score. `None` = all. Restricting to a subset
        # (e.g. {"quality"}) skips the other LLM axes' calls — the per-axis
        # isolation that keeps a spike a handful of calls, not the full matrix.
        # The deterministic token + contract axes are free and always run.
        self._axes = axes
        if output_dir is None:
            output_dir = Path("eval/runs") / datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        self._output_dir = Path(output_dir)

    def _axis_on(self, name: str) -> bool:
        return self._axes is None or name in self._axes

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
                row = await self._run_one(entry, system, traces_root)
                row.provider = self._provider  # provenance stamp (ADR-0016)
                return row

        # Attach bench handlers (LiveSink) to the `a2web` logger for the whole
        # matrix run — every cell's CellStarted/CellEnded and the orchestrator's
        # stage events route to them while attached.
        with _log_ambient(handlers=self._handlers):
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
            provider=self._provider,
            extraction_cache_bypassed=self._extraction_cache_bypassed,
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

        # Bench-cell envelope: every codepath out of this function emits
        # exactly one CellStarted at the top and one CellEnded at exit.
        t0 = time.perf_counter()
        await a2web_log.info(
            CellStarted(
                slug=slug,
                system_name=system.name,
                url=entry.url,
                started_at=datetime.now(UTC).isoformat(),
            )
        )

        # 1) Fetch — the a2web orchestrator's `a2kit.log.info(...)` events log
        # unconditionally; the run-level handler attach (see `run()`) routes
        # them to the bench handlers.
        try:
            fetch_result: SystemResult = await system.fetch(url=entry.url, ask=entry.task)
        except Exception as exc:
            await a2web_log.warning("eval_system_failed", slug=slug, system=system.name, error=str(exc))
            fetch_latency_ms = int((time.perf_counter() - t0) * 1000)
            row = _base_row(entry, system.name, answer="")
            row.fetch_latency_ms = fetch_latency_ms
            row.fetch_error = f"system_raised: {exc}"
            row.quality.reason = "skipped_due_to_fetch_error"
            (cell_dir / "row.json").write_text(_row_to_json(row))
            await self._emit_cell_ended(entry, system, row, "system_raised")
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
        _apply_case_contract_axis(row, entry, fetch_result)

        # 3) No answer → judges skipped (judging an empty string is noise).
        if not fetch_result.answer:
            # An empty answer IS a quality result — zero — not an unscored cell.
            row.quality.disposition = AxisDisposition.SCORED
            row.quality.scores = [0] * len(entry.criteria)
            row.quality.overall = 0
            row.quality.reached = False
            row.quality.reasoning = "empty answer from system"
            (cell_dir / "row.json").write_text(_row_to_json(row))
            await self._emit_cell_ended(entry, system, row, "empty_answer")
            return row

        # 4) Clarity + next_links axes — LLM-judged, run when a bench judge is
        # configured AND the axis is selected. Independent of the quality judge
        # so one failing axis does not sink the others. Per-axis isolation skips
        # the unselected LLM axes (their fields stay None).
        if self._axis_on("clarity"):
            await self._score_clarity(row, entry, fetch_result)
        else:
            row.clarity.reason = "axis not selected"
        if self._axis_on("next_links"):
            await self._score_next_links(row, entry, fetch_result, cell_dir)
        else:
            row.next_links.reason = "axis not selected"

        # 5) Answer-quality axis — skipped when not selected.
        if self._axis_on("quality"):
            try:
                verdict: JudgeVerdict = await self._judge.score(
                    task=entry.task,
                    criteria=entry.criteria,
                    answer=fetch_result.answer,
                )
            except JudgeParseError as exc:
                (cell_dir / "judge_raw.txt").write_text(exc.raw_text)
                row.quality.disposition = AxisDisposition.UNSCORED
                row.quality.reason = f"parse_error: {exc}"
                (cell_dir / "row.json").write_text(_row_to_json(row))
                await self._emit_cell_ended(entry, system, row, "judge_failed")
                return row

            row.quality.disposition = AxisDisposition.SCORED
            row.quality.scores = verdict.scores
            row.quality.overall = verdict.overall
            row.quality.reached = verdict.reached
            row.quality.reasoning = verdict.reasoning
            row.quality.cost_usd += verdict.cost_usd
            row.quality.latency_ms = verdict.latency_ms
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
        else:
            row.quality.reason = "axis not selected"
        (cell_dir / "row.json").write_text(_row_to_json(row))
        await self._emit_cell_ended(entry, system, row, None)
        return row

    async def _emit_cell_ended(
        self,
        entry: CorpusEntry,
        system: EvalSystem,
        row: EvalRow,
        failure_reason: FailureReason | None,
    ) -> None:
        """One emission site for CellEnded — every exit path of _run_one
        funnels here. `failure_reason=None` means ok; anything else is fail."""
        ok = failure_reason is None
        cost = row.fetch_cost_usd + row.quality.cost_usd
        meta = row.fetch_metadata or {}
        cache_hit = bool(meta.get("cache_hit", False))
        tier_value = meta.get("tier") or meta.get("winning_tier")
        tier_str = str(tier_value) if tier_value else None
        await a2web_log.info(
            CellEnded(
                slug=entry.slug,
                system_name=system.name,
                url=entry.url,
                total_ms=row.fetch_latency_ms,
                verdict="ok" if ok else "fail",
                failure_reason=failure_reason,
                cost_usd=cost,
                cache_hit=cache_hit,
                tier=tier_str,
            )
        )

    async def _score_clarity(self, row: EvalRow, entry: CorpusEntry, fetch_result: SystemResult) -> None:
        """Output-clarity axis — graded for every system on every cell with a
        non-empty answer.

        No bench judge is `not_applicable` (the axis was never available); a
        judge that failed to parse is `unscored` (it was asked for and gave
        nothing). Both used to leave `clarity_score` at None.
        """
        if self._bench_judge is None:
            row.clarity.reason = "no bench judge configured"
            return
        try:
            verdict = await self._bench_judge.score_clarity(task=entry.task, answer=fetch_result.answer)
        except JudgeParseError as exc:
            await a2web_log.warning("clarity_judge_failed", slug=entry.slug, system=row.system, error=str(exc))
            row.clarity.mark_unscored(f"parse_error: {exc}")
            return
        row.clarity.mark_scored(score=verdict.score, reasoning=verdict.reasoning)
        row.quality.cost_usd += verdict.cost_usd

    async def _score_next_links(
        self,
        row: EvalRow,
        entry: CorpusEntry,
        fetch_result: SystemResult,
        cell_dir: Path,
    ) -> None:
        """next_links_picked_correctly axis — graded only on entries that ask
        for it, for systems that actually produced a candidate block.

        The three no-score paths were one silent `return` each. They are now
        three distinct records, because "the corpus did not ask", "no judge was
        configured", and "the system emitted a set the harness could not find"
        are not the same fact — and it was the third, unnamed, that hid the
        ADR-0015 rename.
        """
        if not entry.next_links_expected:
            row.next_links.reason = "corpus entry does not expect next_links"
            return
        if self._bench_judge is None:
            row.next_links.reason = "no bench judge configured"
            return
        block = _candidate_block(fetch_result, system=row.system)
        if block is None:
            row.next_links.mark_unscored(
                f"system produced no candidate block under {_CANDIDATE_FIELD[row.system]!r}",
            )
            return
        try:
            verdict = await self._bench_judge.score_next_links(task=entry.task, next_links=block)
        except JudgeParseError as exc:
            await a2web_log.warning("next_links_judge_failed", slug=entry.slug, system=row.system, error=str(exc))
            row.next_links.mark_unscored(f"parse_error: {exc}")
            return
        row.next_links.mark_scored(score=verdict.score, reasoning=verdict.reasoning)
        row.quality.cost_usd += verdict.cost_usd
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
    )


def _apply_token_axis(row: EvalRow, fetch_result: SystemResult) -> None:
    """Read the envelope token breakdown the system recorded in metadata."""
    tokens = fetch_result.metadata.get("envelope_tokens")
    if not isinstance(tokens, dict):
        row.tokens.reason = "system recorded no envelope_tokens"
        return
    total = tokens.get("total")
    per_field = tokens.get("per_field")
    row.tokens.disposition = AxisDisposition.SCORED
    row.tokens.total = int(total) if isinstance(total, int) else 0
    row.tokens.by_field = dict(per_field) if isinstance(per_field, dict) else {}


def _apply_contract_axis(row: EvalRow, fetch_result: SystemResult, requested_url: str) -> None:
    """Run the deterministic envelope contract check for both the debug=False
    and debug=True envelopes the system recorded.

    Systems without a structured envelope (WebFetch) are `not_applicable` with
    a stated reason, rather than carrying a None that also means "not scored".
    """
    for key, axis, debug in (
        ("envelope", row.contract, False),
        ("envelope_debug", row.contract_debug, True),
    ):
        envelope = fetch_result.metadata.get(key)
        if not isinstance(envelope, dict):
            axis.reason = f"system recorded no {key} to check"
            continue
        result = check_envelope_contract(envelope, requested_url=requested_url, debug=debug)
        axis.disposition = AxisDisposition.SCORED
        axis.conformant = result.conformant
        axis.violations = result.violations


#: The live bench cannot observe what the cassette spy sees, so the per-case
#: vocabulary runs minus those keys — and a case that uses one is reported as
#: UNSCORED with the key named, never as a pass.
_BENCH_CONTRACT_KEYS = CONTRACT_KEYS - REPLAY_ONLY_KEYS


def _observe_for_contract(fetch_result: SystemResult) -> dict[str, Any]:
    """Project a live `SystemResult` into the `case_contract` vocabulary's keys.

    Deliberately the SAME key names `replay.observe` produces — that identity is
    what makes one `contract:` block mean the same thing offline and live. The
    two projections differ only in their source (a `FetchResponse` there, the
    recorded envelope here), never in their vocabulary.
    """
    env = fetch_result.metadata.get("envelope")
    env = env if isinstance(env, dict) else {}
    hints = env.get("operator_hints") or []
    # The `query` envelope withholds the body by default (ADR-0015), so
    # `env["content_md"]` is empty for `a2web_extract` — which would make
    # `has_content` and `content_includes` read a blank page and quietly mean
    # nothing. The system records the retrieved body alongside; prefer it.
    content = env.get("content_md") or fetch_result.metadata.get("content_md") or ""
    return {
        # `tier`/`status` are deviation-only on the wire: absent means the
        # boring default, so re-supply it rather than reporting None and
        # failing every case that pins the common path.
        "tier": env.get("tier", fetch_result.metadata.get("tier") or "raw"),
        "status": env.get("status", "ok"),
        "has_content": bool(content),
        "content_md": content,
        "answer": env.get("answer") or fetch_result.answer or "",
        "answer_present": bool(env.get("answer") or fetch_result.answer),
        "narrative": env.get("narrative") or "",
        "narrative_present": bool(env.get("narrative")),
        "retrieval_incomplete": bool(env.get("retrieval_incomplete")),
        "tokens_full": int(fetch_result.metadata.get("envelope_tokens_total") or 0),
        "next_links_count": _candidate_count(fetch_result),
        "operator_hints": sorted(h.get("code", "") for h in hints if isinstance(h, dict)),
        # Severity is carried SEPARATELY from the code list rather than folded
        # into it. ADR-0009's loudest signal is a severity, and a case that
        # could only pin the code would stay green through the exact regression
        # that shipped once already (a `critical` hint reaching the agent
        # unmarked because a quieter hint preceded it in the TSV table).
        "hint_severities": {h.get("code", ""): h.get("severity", "info") for h in hints if isinstance(h, dict)},
        "confidence": env.get("confidence"),
        # The page's own address — a legitimate thing for the answer to cite,
        # and deviation-only on the wire, so fall back to what was requested.
        "page_url": env.get("url") or fetch_result.metadata.get("requested_url") or "",
        # The ADR-0015 index, structured — see `systems._index_projection` for
        # why this cannot be read off `envelope` (the wire renders it as TSV).
        "index": fetch_result.metadata.get("index") or {},
        # What the PAGE declared about itself (ADR-0018). Absent on the ~83-93%
        # of pages that declare nothing, so `{}` is the common case, not a
        # failure — the contract keys read through `.get(...)` accordingly.
        "declared_entity": env.get("declared_entity") or {},
    }


def _apply_case_contract_axis(row: EvalRow, entry: CorpusEntry, fetch_result: SystemResult) -> None:
    """Check the corpus entry's own deterministic expectations, if it states any.

    This is the half `make bench` was missing. A case knew perfectly well that
    its URL is a wall — that `status` must be `failed` and `try_user_browser`
    must fire — and had nowhere to say so except `criteria` prose handed to an
    LLM judge. So a deterministic fact was being scored probabilistically, at
    cost, or not at all. The offline replay corpus has asserted exactly these
    keys for months; this makes the live corpus able to state them too, in the
    same words.
    """
    axis = row.case_contract
    contract = entry.extra.get("contract")
    if not contract:
        axis.reason = "case states no deterministic contract"
        return
    if not isinstance(contract, dict):
        axis.disposition = AxisDisposition.SCORED
        axis.conformant = False
        axis.violations = [f"`contract:` must be a mapping, got {type(contract).__name__}"]
        return
    if fetch_result.metadata.get("envelope") is None:
        axis.reason = "system records no structured envelope (e.g. WebFetch)"
        return

    failures, unsupported = check_contract_keys(contract, _observe_for_contract(fetch_result), supported=_BENCH_CONTRACT_KEYS)
    if unsupported:
        # Not a failure and NOT a pass: the bench genuinely cannot see these.
        axis.reason = f"replay-only keys, not observable live: {sorted(unsupported)}"
        if not failures:
            return
    axis.disposition = AxisDisposition.SCORED
    axis.conformant = not failures
    axis.violations = failures


#: System name -> the envelope field carrying its "what to fetch next" set.
#:
#: LITERAL on purpose, in the spirit of `wire._TSV_FIELDS`. ADR-0015 folded
#: `next_links` and `try_url` into `other_pages` on the `query` envelope while
#: `fetch_raw` kept `next_links`; the reader assumed one name across systems,
#: found it on neither, and scored nothing for five weeks without saying so.
#:
#: A tolerant lookup (try one, fall back to the other) would have absorbed that
#: rename silently and kept producing numbers, which is worse — a wrong number
#: outranks a missing one in how confidently it is acted on.
#:
#: `None` means the system has no structured candidate set at all. Declared
#: rather than omitted: absence from this table is a build-time failure, so a
#: new system cannot join the matrix with a quietly unscorable axis.
_CANDIDATE_FIELD: dict[str, str | None] = {
    "a2web_extract": "other_pages",
    "a2web_detail": "next_links",
    "webfetch_baseline": None,
}


def _candidate_block(fetch_result: SystemResult, *, system: str) -> str | None:
    """The rendered "what to fetch next" block for `system`, or None when the
    system produced none.

    Raises on an unregistered system rather than returning None, because
    "unknown system" and "system produced nothing" must not share an outcome.
    """
    if system not in _CANDIDATE_FIELD:
        raise KeyError(
            f"eval system {system!r} is not in _CANDIDATE_FIELD, so the next_links axis "
            "cannot know which envelope field carries its candidate set. Add an entry "
            "(use None if the system has no structured envelope)."
        )
    field_name = _CANDIDATE_FIELD[system]
    if field_name is None:
        return None
    envelope = fetch_result.metadata.get("envelope")
    if isinstance(envelope, dict):
        block = envelope.get(field_name)
        if isinstance(block, str) and block.strip():
            return block
    return None


def _candidate_count(fetch_result: SystemResult) -> int:
    """Rows in the system's candidate block — the live analogue of replay's
    `next_links_count`.

    The block is TSV with a header line (`wire` renders the list that way), so
    the count is lines-minus-header. Systems with no structured candidate set
    return 0, which is why `next_links_min` should only be pinned on a case
    whose system has one — the vocabulary cannot tell "no candidates" from "no
    such field" and must not pretend to.
    """
    block = _candidate_block(fetch_result, system=fetch_result.system)
    if not block:
        return 0
    lines = [ln for ln in block.splitlines() if ln.strip()]
    return max(0, len(lines) - 1)


def row_as_flat_dict(row: EvalRow) -> dict[str, Any]:
    """The flat per-cell record written to `row.json`, `results.json`, and TSV.

    Flattening happens HERE, at the write boundary, not on the model. Every
    axis contributes its disposition alongside its value, so a consumer reading
    `next_links_score: null` can always see whether the cell was asked.
    """
    return {
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
        "quality_disposition": str(row.quality.disposition),
        "quality_reason": row.quality.reason,
        "judge_scores": row.quality.scores,
        "judge_overall": row.quality.overall,
        "judge_reached": row.quality.reached,
        "judge_reasoning": row.quality.reasoning,
        "judge_cost_usd": row.quality.cost_usd,
        "judge_latency_ms": row.quality.latency_ms,
        "tokens_disposition": str(row.tokens.disposition),
        "envelope_tokens_total": row.tokens.total,
        "envelope_tokens_by_field": row.tokens.by_field,
        "case_contract_disposition": str(row.case_contract.disposition),
        "case_contract_conformant": row.case_contract.conformant,
        "case_contract_violations": row.case_contract.violations,
        "case_contract_reason": row.case_contract.reason,
        "contract_disposition": str(row.contract.disposition),
        "contract_conformant": row.contract.conformant,
        "contract_violations": row.contract.violations,
        "contract_debug_disposition": str(row.contract_debug.disposition),
        "contract_conformant_debug": row.contract_debug.conformant,
        "contract_violations_debug": row.contract_debug.violations,
        "clarity_disposition": str(row.clarity.disposition),
        "clarity_reason": row.clarity.reason,
        "clarity_score": row.clarity.score,
        "clarity_reasoning": row.clarity.reasoning,
        "next_links_disposition": str(row.next_links.disposition),
        "next_links_reason": row.next_links.reason,
        "next_links_score": row.next_links.score,
        "next_links_reasoning": row.next_links.reasoning,
        "provider": row.provider,
    }


def _row_to_json(row: EvalRow) -> str:
    return json.dumps(row_as_flat_dict(row), indent=2, default=str)


__all__ = [
    "AxisCoverage",
    "AxisDisposition",
    "ContractAxis",
    "EvalReport",
    "EvalRow",
    "EvalSuite",
    "QualityAxis",
    "ScoreAxis",
    "TokenAxis",
    "row_as_flat_dict",
]
