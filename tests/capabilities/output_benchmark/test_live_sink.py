"""LiveSink + cell-event capability tests.

Invariants asserted (from openspec/changes/bench-live-sink-v1/specs):

- every (entry, system) cell emits exactly one CellStarted + one CellEnded.
- failure path still emits exactly one CellEnded carrying verdict="fail"
  and a non-None failure_reason.
- LiveSink renders one line per event with monotonically increasing
  [i/N] counter in completion order.
- start-line for a cell appears earlier in stdout than its matching end-line.
- no heartbeat fires after the run completes.
"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import asdict
from pathlib import Path

import pytest
from a2kit.packages.ldd import LddEmission

from a2web.llm_eval.corpus import load_corpus
from a2web.llm_eval.events import CellEnded, CellStarted
from a2web.llm_eval.live_sink import LiveSink
from a2web.llm_eval.runner import EvalSuite
from a2web.llm_eval.systems import SystemResult

from .test_output_benchmark import _MockBenchJudge, _MockJudge


class _CapturingSink:
    """Test sink that records every emission for invariant assertions."""

    def __init__(self) -> None:
        self.emissions: list[LddEmission] = []

    async def __call__(self, emission: LddEmission) -> None:
        self.emissions.append(emission)


class _StubOk:
    name = "stubOk"

    async def fetch(self, *, url: str, ask: str) -> SystemResult:
        return SystemResult(answer="ok body", system=self.name, latency_ms=12, cost_usd=0.001)


class _StubRaises:
    name = "stubRaise"

    async def fetch(self, *, url: str, ask: str) -> SystemResult:
        raise RuntimeError("boom")


def _two_by_two_corpus(tmp_path: Path) -> Path:
    body = """
urls:
  - slug: a
    url: https://example.com/a
    class: clean
    task: do a thing
    criteria: [c1]
  - slug: b
    url: https://example.com/b
    class: clean
    task: do b thing
    criteria: [c1]
"""
    p = tmp_path / "corpus.yaml"
    p.write_text(body)
    return p


@pytest.mark.asyncio
async def test_every_cell_emits_one_start_and_one_end(tmp_path: Path) -> None:
    corpus = load_corpus(_two_by_two_corpus(tmp_path))
    capture = _CapturingSink()
    suite = EvalSuite(
        corpus=corpus,
        systems=[_StubOk(), _StubOk()],
        judge=_MockJudge(),
        bench_judge=_MockBenchJudge(),
        output_dir=tmp_path / "out",
        sinks=(capture,),
    )
    await suite.run()

    started = [e for e in capture.emissions if e.name == "CellStarted"]
    ended = [e for e in capture.emissions if e.name == "CellEnded"]
    assert len(started) == 4, started
    assert len(ended) == 4, ended

    pairs = {(e.payload["slug"], e.payload["system_name"]) for e in started}
    end_pairs = {(e.payload["slug"], e.payload["system_name"]) for e in ended}
    assert pairs == end_pairs == {("a", "stubOk"), ("b", "stubOk")}


@pytest.mark.asyncio
async def test_failing_cell_still_emits_cell_ended_with_fail(tmp_path: Path) -> None:
    corpus = load_corpus(_two_by_two_corpus(tmp_path))
    capture = _CapturingSink()
    suite = EvalSuite(
        corpus=corpus,
        systems=[_StubRaises()],
        judge=_MockJudge(),
        bench_judge=_MockBenchJudge(),
        output_dir=tmp_path / "out",
        sinks=(capture,),
    )
    await suite.run()

    ended = [e for e in capture.emissions if e.name == "CellEnded"]
    assert len(ended) == 2  # 2 corpus x 1 system
    for e in ended:
        assert e.payload["verdict"] == "fail"
        assert e.payload["failure_reason"] == "system_raised"


@pytest.mark.asyncio
async def test_live_sink_renders_one_line_per_event(tmp_path: Path) -> None:
    corpus = load_corpus(_two_by_two_corpus(tmp_path))
    buf = io.StringIO()
    # Heartbeat interval well above test wall time so it never fires here.
    sink = LiveSink(total=4, stream=buf, heartbeat_interval_s=3600.0)
    suite = EvalSuite(
        corpus=corpus,
        systems=[_StubOk(), _StubOk()],
        judge=_MockJudge(),
        bench_judge=_MockBenchJudge(),
        output_dir=tmp_path / "out",
        sinks=(sink,),
    )
    async with sink:
        await suite.run()

    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    # 4 cells x (start + end) = 8 lines.
    assert len(lines) == 8, lines

    end_lines = [ln for ln in lines if "/4]" in ln]
    assert len(end_lines) == 4
    counters = [int(re.search(r"\[(\d+)/4\]", ln).group(1)) for ln in end_lines]
    assert counters == [1, 2, 3, 4], counters


@pytest.mark.asyncio
async def test_start_line_precedes_end_line_for_each_cell(tmp_path: Path) -> None:
    corpus = load_corpus(_two_by_two_corpus(tmp_path))
    buf = io.StringIO()
    sink = LiveSink(total=2, stream=buf, heartbeat_interval_s=3600.0)
    suite = EvalSuite(
        corpus=corpus,
        systems=[_StubOk()],
        judge=_MockJudge(),
        bench_judge=_MockBenchJudge(),
        output_dir=tmp_path / "out",
        sinks=(sink,),
    )
    async with sink:
        await suite.run()

    lines = buf.getvalue().splitlines()
    for slug in ("a", "b"):
        slug_lines = [(i, ln) for i, ln in enumerate(lines) if slug in ln]
        # Two lines per slug — start (no counter), end (with counter).
        assert len(slug_lines) >= 2
        start_idx = next(i for i, ln in slug_lines if "start" in ln)
        end_idx = next(i for i, ln in slug_lines if "/2]" in ln)
        assert start_idx < end_idx, (slug, start_idx, end_idx)


@pytest.mark.asyncio
async def test_no_heartbeat_after_run_completes(tmp_path: Path) -> None:
    corpus = load_corpus(_two_by_two_corpus(tmp_path))
    buf = io.StringIO()
    # Short heartbeat interval so we can verify NO heartbeat fires post-exit.
    sink = LiveSink(total=2, stream=buf, heartbeat_interval_s=0.05)
    suite = EvalSuite(
        corpus=corpus,
        systems=[_StubOk()],
        judge=_MockJudge(),
        bench_judge=_MockBenchJudge(),
        output_dir=tmp_path / "out",
        sinks=(sink,),
    )
    async with sink:
        await suite.run()
    # After __aexit__ returns, no further writes should occur.
    snapshot = buf.getvalue()
    await asyncio.sleep(0.2)
    assert buf.getvalue() == snapshot


def test_cell_events_are_frozen_dataclasses() -> None:
    started = CellStarted(slug="a", system_name="s", url="https://x", started_at="2026-01-01T00:00:00+00:00")
    ended = CellEnded(
        slug="a",
        system_name="s",
        url="https://x",
        total_ms=10,
        verdict="ok",
        failure_reason=None,
        cost_usd=0.0,
        cache_hit=False,
        tier=None,
    )
    # asdict must work for a2kit's typed-emit payload extraction.
    assert asdict(started)["slug"] == "a"
    assert asdict(ended)["verdict"] == "ok"
    with pytest.raises(Exception):  # noqa: B017 — FrozenInstanceError
        started.slug = "z"  # type: ignore[misc]
