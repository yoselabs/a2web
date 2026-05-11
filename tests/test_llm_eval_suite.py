"""v0.4 step 5: EvalSuite + corpus + report tests.

End-to-end with mock systems + a mock judge — no real API, no network.
Exercises:
- Corpus loader: required-field validation, optional-field passthrough.
- Suite run: matrix expansion, ordering, trace persistence, error rows.
- Report writer: results.tsv, manifest.json, leaderboard.md, cost.md,
  findings.md, corpus.frozen.yaml.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from a2web.llm import (
    Judge,
    JudgeParseError,
    JudgeVerdict,
    ModelSpec,
)
from a2web.llm.eval import (
    CorpusError,
    EvalSuite,
    SystemResult,
    load_corpus,
    stats_dict,
    write_all,
)

# --------------------------------------------------------------------- #
# Corpus tests
# --------------------------------------------------------------------- #


def _write_corpus(tmp: Path, content: str) -> Path:
    path = tmp / "corpus.yaml"
    path.write_text(content)
    return path


def test_load_corpus_happy_path(tmp_path: Path) -> None:
    body = """
urls:
  - slug: hn
    url: https://news.ycombinator.com/
    class: A_clean
    task: List the top 5 stories.
    needs: [content+links]
    criteria:
      - Identifies 5 stories
      - Has source domains
  - slug: arxiv
    url: https://arxiv.org/abs/2401.05566
    class: A_clean
    task: Who are the authors?
    criteria:
      - Lists author names
"""
    p = _write_corpus(tmp_path, body)
    corpus = load_corpus(p)

    assert len(corpus) == 2
    e0 = corpus.entries[0]
    assert e0.slug == "hn"
    assert e0.url_class == "A_clean"
    assert e0.criteria == ["Identifies 5 stories", "Has source domains"]
    assert e0.needs == ["content+links"]
    assert corpus.entries[1].slug == "arxiv"
    assert corpus.entries[1].needs == []  # missing → empty list


def test_load_corpus_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CorpusError) as ei:
        load_corpus(tmp_path / "nope.yaml")
    assert "not found" in str(ei.value)


def test_load_corpus_empty_urls(tmp_path: Path) -> None:
    p = _write_corpus(tmp_path, "urls: []")
    with pytest.raises(CorpusError):
        load_corpus(p)


def test_load_corpus_missing_required_field(tmp_path: Path) -> None:
    body = """
urls:
  - slug: x
    url: https://example.com/
    task: Q
    # missing criteria
"""
    p = _write_corpus(tmp_path, body)
    with pytest.raises(CorpusError):
        load_corpus(p)


def test_load_corpus_empty_criteria(tmp_path: Path) -> None:
    body = """
urls:
  - slug: x
    url: https://example.com/
    task: Q
    criteria: []
"""
    p = _write_corpus(tmp_path, body)
    with pytest.raises(CorpusError):
        load_corpus(p)


# --------------------------------------------------------------------- #
# Mock systems + judge for the suite tests
# --------------------------------------------------------------------- #


class _ConstantSystem:
    """System returning a configured SystemResult regardless of input."""

    def __init__(self, *, name: str, answer: str, error: str | None = None) -> None:
        self.name = name
        self._answer = answer
        self._error = error
        self.calls: list[dict] = []

    async def fetch(self, *, url: str, ask: str) -> SystemResult:
        self.calls.append({"url": url, "ask": ask})
        return SystemResult(
            answer=self._answer,
            system=self.name,
            latency_ms=10,
            cost_usd=0.001,
            prompt_tokens=50,
            completion_tokens=20,
            error=self._error,
            metadata={"x": 1},
        )


class _RaisingSystem:
    """System that raises an exception on fetch. Suite should record this."""

    name = "raiser"

    async def fetch(self, *, url: str, ask: str) -> SystemResult:
        raise RuntimeError("simulated system failure")


class _MockJudge(Judge):
    """Subclass that bypasses the provider call with canned verdicts."""

    def __init__(self, *, answers_to_score: dict[str, int] | None = None) -> None:
        # Skip parent's provider — we don't need it.
        self._answers_to_score = answers_to_score or {}
        self._model = ModelSpec("mock", "judge-mock")
        self._max_tokens = 512

    async def score(
        self, *, task: str, criteria: list[str], answer: str
    ) -> JudgeVerdict:
        overall = self._answers_to_score.get(answer, 3)
        return JudgeVerdict(
            scores=[overall] * len(criteria),
            overall=overall,
            reached=overall >= 1,
            reasoning=f"mock judge for {answer[:30]!r}",
            model="judge-mock",
            cost_usd=0.002,
            latency_ms=15,
        )


class _ParseErrorJudge(Judge):
    """Judge that always raises JudgeParseError — exercises the error path."""

    def __init__(self) -> None:
        self._model = ModelSpec("mock", "judge-mock")
        self._max_tokens = 512

    async def score(
        self, *, task: str, criteria: list[str], answer: str
    ) -> JudgeVerdict:
        raise JudgeParseError("synthetic", raw_text="garbage")


# --------------------------------------------------------------------- #
# EvalSuite tests
# --------------------------------------------------------------------- #


def _two_url_corpus(tmp_path: Path) -> Path:
    body = """
urls:
  - slug: hn
    url: https://news.ycombinator.com/
    class: A_clean
    task: List stories
    criteria: [count, order]
  - slug: arxiv
    url: https://arxiv.org/abs/2401.05566
    class: A_clean
    task: Authors?
    criteria: [names]
"""
    return _write_corpus(tmp_path, body)


@pytest.mark.asyncio
async def test_suite_runs_full_matrix(tmp_path: Path) -> None:
    corpus = load_corpus(_two_url_corpus(tmp_path))
    a = _ConstantSystem(name="alpha", answer="alpha answer")
    b = _ConstantSystem(name="beta", answer="beta answer")
    judge = _MockJudge(answers_to_score={"alpha answer": 5, "beta answer": 3})

    suite = EvalSuite(
        corpus=corpus,
        systems=[a, b],
        judge=judge,
        concurrency=2,
        output_dir=tmp_path / "out",
    )
    report = await suite.run()

    # 2 URLs x 2 systems = 4 rows
    assert len(report.rows) == 4
    assert {r.system for r in report.rows} == {"alpha", "beta"}
    assert all(r.judge_overall is not None for r in report.rows)
    assert all(r.judge_error is None for r in report.rows)

    # Each system received 2 calls (one per corpus URL)
    assert len(a.calls) == 2
    assert len(b.calls) == 2

    # Per-cell trace files written
    for r in report.rows:
        cell = report.output_dir / "trace" / r.slug / r.system
        assert (cell / "answer.txt").exists()
        assert (cell / "fetch_result.json").exists()
        assert (cell / "judge.json").exists()
        assert (cell / "row.json").exists()


@pytest.mark.asyncio
async def test_suite_records_fetch_errors_as_rows(tmp_path: Path) -> None:
    """A system that raises during fetch produces a row with fetch_error set
    and the judge step skipped."""
    corpus = load_corpus(_two_url_corpus(tmp_path))
    ok = _ConstantSystem(name="ok", answer="ok answer")
    bad = _RaisingSystem()
    judge = _MockJudge()

    suite = EvalSuite(
        corpus=corpus,
        systems=[ok, bad],
        judge=judge,
        output_dir=tmp_path / "out",
    )
    report = await suite.run()

    bad_rows = [r for r in report.rows if r.system == "raiser"]
    assert len(bad_rows) == 2
    for r in bad_rows:
        assert r.fetch_error is not None
        assert "simulated system failure" in r.fetch_error
        assert r.judge_overall is None
        assert r.judge_error == "skipped_due_to_fetch_error"


@pytest.mark.asyncio
async def test_suite_handles_empty_answer(tmp_path: Path) -> None:
    """System returning an empty answer → judge skipped, row marked
    reached=False with overall=0."""
    corpus = load_corpus(_two_url_corpus(tmp_path))
    empty = _ConstantSystem(name="empty", answer="", error="no content")
    judge = _MockJudge()

    suite = EvalSuite(
        corpus=corpus,
        systems=[empty],
        judge=judge,
        output_dir=tmp_path / "out",
    )
    report = await suite.run()

    assert len(report.rows) == 2
    for r in report.rows:
        assert r.judge_overall == 0
        assert r.judge_reached is False
        assert r.judge_reasoning == "empty answer from system"


@pytest.mark.asyncio
async def test_suite_records_judge_parse_errors(tmp_path: Path) -> None:
    """JudgeParseError on a row → judge_error populated, judge_overall None,
    judge_raw.txt saved in trace."""
    corpus = load_corpus(_two_url_corpus(tmp_path))
    sys_a = _ConstantSystem(name="a", answer="answer text")
    judge = _ParseErrorJudge()

    suite = EvalSuite(
        corpus=corpus,
        systems=[sys_a],
        judge=judge,
        output_dir=tmp_path / "out",
    )
    report = await suite.run()

    for r in report.rows:
        assert r.judge_error is not None
        assert "parse_error" in r.judge_error
        assert r.judge_overall is None
        raw_path = report.output_dir / "trace" / r.slug / r.system / "judge_raw.txt"
        assert raw_path.exists()
        assert raw_path.read_text() == "garbage"


def test_suite_requires_at_least_one_system(tmp_path: Path) -> None:
    corpus = load_corpus(_two_url_corpus(tmp_path))
    judge = _MockJudge()
    with pytest.raises(ValueError):
        EvalSuite(corpus=corpus, systems=[], judge=judge)


# --------------------------------------------------------------------- #
# Report writer tests
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_report_writes_all_expected_artifacts(tmp_path: Path) -> None:
    corpus_path = _two_url_corpus(tmp_path)
    corpus = load_corpus(corpus_path)
    a = _ConstantSystem(name="alpha", answer="alpha answer")
    b = _ConstantSystem(name="beta", answer="beta answer")
    judge = _MockJudge(answers_to_score={"alpha answer": 5, "beta answer": 3})

    suite = EvalSuite(
        corpus=corpus,
        systems=[a, b],
        judge=judge,
        output_dir=tmp_path / "out",
    )
    report = await suite.run()
    write_all(report)

    out = report.output_dir
    # All artifacts present
    assert (out / "results.tsv").exists()
    assert (out / "manifest.json").exists()
    assert (out / "leaderboard.md").exists()
    assert (out / "cost.md").exists()
    assert (out / "findings.md").exists()
    assert (out / "corpus.frozen.yaml").exists()

    # results.tsv has the right shape: header + 4 rows
    lines = (out / "results.tsv").read_text().strip().splitlines()
    assert len(lines) == 5  # 1 header + 4 rows
    assert "slug" in lines[0] and "judge_overall" in lines[0]

    # manifest.json carries the systems list + wall_seconds
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["systems"] == ["alpha", "beta"]
    assert manifest["row_count"] == 4
    assert manifest["wall_seconds"] >= 0

    # leaderboard.md mentions both systems
    leaderboard = (out / "leaderboard.md").read_text()
    assert "alpha" in leaderboard
    assert "beta" in leaderboard

    # cost.md totals match per-system breakdown
    cost = (out / "cost.md").read_text()
    assert "alpha" in cost
    assert "beta" in cost

    # findings.md groups reach counts
    findings = (out / "findings.md").read_text()
    assert "alpha" in findings

    # corpus.frozen.yaml is a verbatim copy
    frozen = yaml.safe_load((out / "corpus.frozen.yaml").read_text())
    assert frozen == yaml.safe_load(corpus_path.read_text())


@pytest.mark.asyncio
async def test_stats_dict_summarizes_run(tmp_path: Path) -> None:
    corpus = load_corpus(_two_url_corpus(tmp_path))
    a = _ConstantSystem(name="alpha", answer="alpha answer")
    judge = _MockJudge(answers_to_score={"alpha answer": 4})

    suite = EvalSuite(
        corpus=corpus,
        systems=[a],
        judge=judge,
        output_dir=tmp_path / "out",
    )
    report = await suite.run()
    stats = stats_dict(report)

    assert stats["rows"] == 2
    assert stats["systems"] == ["alpha"]
    assert stats["mean_overall_by_system"]["alpha"] == pytest.approx(4.0)
    assert stats["total_cost_usd"] > 0
