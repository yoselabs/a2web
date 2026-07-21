"""Output-benchmark capability tests.

Covers the four measurement axes the benchmark adds on top of the eval
matrix — token cost, data-contract conformance, output clarity, and the
`next_links` axis — plus provider selection and a full in-process suite run.
No real API calls, no live network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from anyllm import ClaudeCodeSdkAdapter

from a2web.llm_eval import (
    BenchJudge,
    ClarityVerdict,
    EvalSuite,
    NextLinksVerdict,
    SystemResult,
    check_envelope_contract,
    envelope_token_breakdown,
    estimate_tokens,
    load_corpus,
    stats_dict,
    write_all,
)
from a2web.llm_eval.__main__ import _pick_provider
from a2web.packages.llm_extract import (
    Judge,
    JudgeVerdict,
    ModelSpec,
    ProviderResponse,
)

# --------------------------------------------------------------------- #
# Provider selection — task 2.3
# --------------------------------------------------------------------- #


def test_pick_provider_defaults_to_claude_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A2WEB_BENCH_PROVIDER", raising=False)
    # Simulate a Claude Code session being present — otherwise `available()`
    # (session-credential probe) returns False in a session-less CI runner and
    # `auto` correctly skips the rung. This test asserts the SELECTION order, not
    # the environment probe, so pin availability deterministically.
    monkeypatch.setattr(ClaudeCodeSdkAdapter, "available", lambda _self: True)
    from a2web.settings import AppSettings

    provider, provider_id = _pick_provider(AppSettings())
    assert provider_id == "claude-code"
    assert isinstance(provider, ClaudeCodeSdkAdapter)


def test_pick_provider_honours_claude_code_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A2WEB_BENCH_PROVIDER", "claude-code")
    # Same session-present pin as the default-selection test (CI has no session).
    monkeypatch.setattr(ClaudeCodeSdkAdapter, "available", lambda _self: True)
    from a2web.settings import AppSettings

    provider, provider_id = _pick_provider(AppSettings())
    assert provider_id == "claude-code"
    assert isinstance(provider, ClaudeCodeSdkAdapter)


def test_pick_provider_honours_anthropic_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """`A2WEB_BENCH_PROVIDER=anthropic` forces the API provider. Stub the
    manifest-registry lookup so the test does not need a real key."""

    class _FakeAnthropic:
        name = "anthropic"

    fake = _FakeAnthropic()

    def _fake_load_surface(_path: str, _protocol: object, _settings: object) -> dict:
        return {"anthropic": fake}

    from a2web.settings import AppSettings

    monkeypatch.setenv("A2WEB_BENCH_PROVIDER", "anthropic")
    # Selection now flows through `llm_resource.select_provider`, which loads
    # the registry via `a2web._plugin.load_surface` (function-local import).
    monkeypatch.setattr("a2web._plugin.load_surface", _fake_load_surface)
    provider, provider_id = _pick_provider(AppSettings())
    assert provider_id == "anthropic"
    assert isinstance(provider, _FakeAnthropic)


# --------------------------------------------------------------------- #
# Token-cost axis — task 3.3
# --------------------------------------------------------------------- #


def test_estimate_tokens_empty_and_nonempty() -> None:
    assert estimate_tokens("") == 0
    # ~4 chars per token.
    assert estimate_tokens("x" * 400) == 100


def test_envelope_token_breakdown_total_and_per_field() -> None:
    envelope = {
        "confidence": "high",
        "content_md": "word " * 200,
        "debug": {"total_ms": 1234, "cache": "miss"},
    }
    tokens = envelope_token_breakdown(envelope)

    assert tokens.total > 0
    # Each top-level field is broken out.
    assert "confidence" in tokens.per_field
    assert "content_md" in tokens.per_field
    assert "debug" in tokens.per_field
    # The nested debug object is broken out per sub-field.
    assert "debug.total_ms" in tokens.per_field
    assert "debug.cache" in tokens.per_field
    # content_md dominates the cost.
    assert tokens.per_field["content_md"] > tokens.per_field["confidence"]


# --------------------------------------------------------------------- #
# Data-contract axis — task 4.2
# --------------------------------------------------------------------- #


def test_contract_conformant_envelope_passes() -> None:
    envelope = {"confidence": "high", "content_md": "body"}
    result = check_envelope_contract(envelope, requested_url="https://e.com/", debug=False)
    assert result.conformant
    assert result.violations == []


def test_contract_leaked_default_tier_fails() -> None:
    result = check_envelope_contract(
        {"confidence": "high", "tier": "raw"},
        requested_url="https://e.com/",
        debug=False,
    )
    assert not result.conformant
    assert any("tier" in v for v in result.violations)


def test_contract_leaked_default_status_fails() -> None:
    result = check_envelope_contract(
        {"confidence": "high", "status": "ok"},
        requested_url="https://e.com/",
        debug=False,
    )
    assert not result.conformant
    assert any("status" in v for v in result.violations)


def test_contract_ungated_debug_fails() -> None:
    result = check_envelope_contract(
        {"confidence": "high", "debug": {"total_ms": 5}},
        requested_url="https://e.com/",
        debug=False,
    )
    assert not result.conformant
    assert any("debug" in v for v in result.violations)


def test_contract_url_equal_to_requested_fails() -> None:
    result = check_envelope_contract(
        {"confidence": "high", "url": "https://e.com/"},
        requested_url="https://e.com/",
        debug=False,
    )
    assert not result.conformant
    assert any("url" in v for v in result.violations)


def test_contract_debug_object_allowed_under_debug_true() -> None:
    result = check_envelope_contract(
        {"confidence": "high", "debug": {"total_ms": 5}},
        requested_url="https://e.com/",
        debug=True,
    )
    assert result.conformant


def test_contract_deviating_tier_and_status_allowed() -> None:
    """Non-default deviation values are legitimate — they carry signal."""
    result = check_envelope_contract(
        {"confidence": "low", "tier": "browser", "status": "failed", "url": "https://e.com/elsewhere"},
        requested_url="https://e.com/",
        debug=False,
    )
    assert result.conformant


# --------------------------------------------------------------------- #
# Output-clarity + next_links judge axes — tasks 5.2, 6.2
# --------------------------------------------------------------------- #


class _CannedProvider:
    """Provider returning a fixed completion payload."""

    name = "canned"

    def __init__(self, payload: str) -> None:
        self._payload = payload

    async def complete(
        self,
        *,
        system: object,
        user: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        thinking_disabled: bool = True,
    ) -> ProviderResponse:
        return ProviderResponse(text=self._payload, model=model)


@pytest.mark.asyncio
async def test_clarity_judge_scores_clean_answer_high() -> None:
    judge = BenchJudge(
        provider=_CannedProvider('{"clarity": 5, "reasoning": "direct and actionable"}'),
        model=ModelSpec("bench-model"),
    )
    verdict = await judge.score_clarity(task="Summarize the page", answer="Clean answer.")
    assert verdict.score == 5
    assert 0 <= verdict.score <= 5


@pytest.mark.asyncio
async def test_clarity_judge_scores_noisy_answer_low() -> None:
    judge = BenchJudge(
        provider=_CannedProvider('{"clarity": 1, "reasoning": "buried under nav chrome"}'),
        model=ModelSpec("bench-model"),
    )
    verdict = await judge.score_clarity(task="Summarize the page", answer="Cookie banner... menu... ad...")
    assert verdict.score == 1


@pytest.mark.asyncio
async def test_clarity_judge_tolerates_missing_reasoning() -> None:
    """Under the unified wobble discipline, a missing `reasoning` no longer
    fails the clarity axis — DEFAULT to "" so the score still counts."""
    judge = BenchJudge(
        provider=_CannedProvider('{"clarity": 4}'),  # reasoning intentionally absent
        model=ModelSpec("bench-model"),
    )
    verdict = await judge.score_clarity(task="?", answer="x")
    assert verdict.score == 4
    assert verdict.reasoning == ""


@pytest.mark.asyncio
async def test_next_links_judge_tolerates_missing_reasoning() -> None:
    """Same wobble discipline for the next_links axis."""
    judge = BenchJudge(
        provider=_CannedProvider('{"next_links_score": 3}'),
        model=ModelSpec("bench-model"),
    )
    verdict = await judge.score_next_links(task="?", next_links="...")
    assert verdict.score == 3
    assert verdict.reasoning == ""


@pytest.mark.asyncio
async def test_next_links_judge_parses_score() -> None:
    judge = BenchJudge(
        provider=_CannedProvider('{"next_links_score": 4, "reasoning": "right drilldown set"}'),
        model=ModelSpec("bench-model"),
    )
    verdict = await judge.score_next_links(task="Find posts about X", next_links="anchor\turl\treason\n…")
    assert verdict.score == 4


# --------------------------------------------------------------------- #
# Mock systems + judges for the suite-level tests
# --------------------------------------------------------------------- #


class _StubSystem:
    """System returning a SystemResult with a synthetic a2web envelope."""

    def __init__(
        self,
        *,
        name: str,
        answer: str,
        next_links_block: str | None = None,
        structured: bool = True,
    ) -> None:
        self.name = name
        self._answer = answer
        self._next_links_block = next_links_block
        self._structured = structured

    async def fetch(self, *, url: str, ask: str) -> SystemResult:
        if not self._structured:
            # WebFetch-shaped — plain text, no structured envelope.
            answer_tokens = estimate_tokens(self._answer)
            return SystemResult(
                answer=self._answer,
                system=self.name,
                latency_ms=5,
                metadata={"envelope_tokens": {"total": answer_tokens, "per_field": {"answer": answer_tokens}}},
            )
        envelope: dict[str, object] = {"confidence": "high", "content_md": self._answer}
        if self._next_links_block:
            envelope["next_links"] = self._next_links_block
        envelope_debug = {**envelope, "debug": {"total_ms": 5}}
        tokens = envelope_token_breakdown(envelope)
        return SystemResult(
            answer=self._answer,
            system=self.name,
            latency_ms=5,
            metadata={
                "envelope": envelope,
                "envelope_debug": envelope_debug,
                "envelope_tokens": {"total": tokens.total, "per_field": tokens.per_field},
            },
        )


class _MockJudge(Judge):
    """Quality judge with a canned verdict — bypasses the provider."""

    def __init__(self) -> None:
        self._model = ModelSpec("judge-mock")
        self._max_tokens = 512

    async def score(self, *, task: str, criteria: list[str], answer: str) -> JudgeVerdict:
        return JudgeVerdict(
            scores=[4] * len(criteria),
            overall=4,
            reached=True,
            reasoning="mock",
            model="judge-mock",
        )


class _MockBenchJudge(BenchJudge):
    """Bench judge with canned verdicts — bypasses the provider."""

    def __init__(self) -> None:
        self._model = ModelSpec("bench-mock")
        self._max_tokens = 256

    async def score_clarity(self, *, task: str, answer: str) -> ClarityVerdict:
        return ClarityVerdict(score=4, reasoning="mock clarity", model="bench-mock")

    async def score_next_links(self, *, task: str, next_links: str) -> NextLinksVerdict:
        return NextLinksVerdict(score=3, reasoning="mock next_links", model="bench-mock")


def _corpus(tmp_path: Path) -> Path:
    """Two-entry corpus: one listing (next_links axis), one permalink."""
    body = """
urls:
  - slug: listing
    url: https://example.com/listing
    class: listing
    next_links_expected: true
    task: List the top items.
    criteria: [count, titles]
  - slug: permalink
    url: https://example.com/article
    class: clean
    task: Summarize the article.
    criteria: [topic]
"""
    path = tmp_path / "corpus.yaml"
    path.write_text(body)
    return path


# --------------------------------------------------------------------- #
# next_links axis applies to listing entries only — task 6.2
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_next_links_axis_scores_listing_not_permalink(tmp_path: Path) -> None:
    corpus = load_corpus(_corpus(tmp_path))
    # Both entries get a system that produces next_links; only the listing
    # entry should be scored on the axis.
    system = _StubSystem(name="a2web", answer="answer body", next_links_block="anchor\turl\treason\nA\thttps://x\twhy")

    suite = EvalSuite(
        corpus=corpus,
        systems=[system],
        judge=_MockJudge(),
        bench_judge=_MockBenchJudge(),
        output_dir=tmp_path / "out",
    )
    report = await suite.run()

    by_slug = {r.slug: r for r in report.rows}
    assert by_slug["listing"].next_links_score == 3
    assert by_slug["permalink"].next_links_score is None
    # Clarity is scored for every cell regardless of listing-ness.
    assert by_slug["listing"].clarity_score == 4
    assert by_slug["permalink"].clarity_score == 4


# --------------------------------------------------------------------- #
# Full suite run carries all four axes — task 7.3
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_suite_run_carries_all_four_axes(tmp_path: Path) -> None:
    corpus = load_corpus(_corpus(tmp_path))
    systems = [
        _StubSystem(name="a2web_detail", answer="a2web answer body " * 20),
        _StubSystem(name="webfetch_baseline", answer="webfetch answer", structured=False),
    ]
    suite = EvalSuite(
        corpus=corpus,
        systems=systems,
        judge=_MockJudge(),
        bench_judge=_MockBenchJudge(),
        output_dir=tmp_path / "out",
    )
    report = await suite.run()
    write_all(report)

    assert len(report.rows) == 4  # 2 URLs x 2 systems
    for row in report.rows:
        # Axis 1 — answer quality.
        assert row.judge_overall == 4
        # Axis 2 — token cost.
        assert row.envelope_tokens_total > 0
        # Axis 4 — output clarity.
        assert row.clarity_score == 4

    # Axis 3 — data-contract conformance: present for a2web, N/A for WebFetch.
    a2web_rows = [r for r in report.rows if r.system == "a2web_detail"]
    webfetch_rows = [r for r in report.rows if r.system == "webfetch_baseline"]
    assert all(r.contract_conformant is True for r in a2web_rows)
    assert all(r.contract_conformant_debug is True for r in a2web_rows)
    assert all(r.contract_conformant is None for r in webfetch_rows)

    # Report carries the axes file and the new TSV columns.
    out = report.output_dir
    assert (out / "axes.md").exists()
    axes = (out / "axes.md").read_text()
    assert "four axes" in axes
    assert "vs WebFetch baseline" in axes

    header = (out / "results.tsv").read_text().splitlines()[0]
    for column in ("envelope_tokens_total", "contract_conformant", "clarity_score", "next_links_score"):
        assert column in header

    # stats_dict surfaces every axis.
    stats = stats_dict(report)
    assert "mean_envelope_tokens_by_system" in stats
    assert "mean_clarity_by_system" in stats
    assert "contract_pass_by_system" in stats
    assert stats["mean_clarity_by_system"]["a2web_detail"] == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_suite_run_persists_axis_traces(tmp_path: Path) -> None:
    corpus = load_corpus(_corpus(tmp_path))
    system = _StubSystem(name="a2web", answer="body", next_links_block="anchor\turl\treason\nA\thttps://x\twhy")
    suite = EvalSuite(
        corpus=corpus,
        systems=[system],
        judge=_MockJudge(),
        bench_judge=_MockBenchJudge(),
        output_dir=tmp_path / "out",
    )
    report = await suite.run()

    # The listing cell persists a next_links trace.
    nl_trace = report.output_dir / "trace" / "listing" / "a2web" / "next_links.json"
    assert nl_trace.exists()
    payload = json.loads(nl_trace.read_text())
    assert payload["score"] == 3


# --------------------------------------------------------------------- #
# ADR-0016 — cost guard, provenance stamping, per-axis/-item isolation
# --------------------------------------------------------------------- #


def test_default_judge_model_denied_on_metered_anthropic() -> None:
    """The bench's default judge model is Sonnet; on metered anthropic it must
    be refused (the $20 regression), yet allowed via the claude-code subscription."""
    from a2web.packages.llm_cost_guard import DEFAULT_POLICY

    assert DEFAULT_POLICY.permits("anthropic", "claude-sonnet-4-6") is False
    assert DEFAULT_POLICY.permits("claude-code", "claude-sonnet-4-6") is True


@pytest.mark.asyncio
async def test_provider_stamped_in_report_and_artifacts(tmp_path: Path) -> None:
    corpus = load_corpus(_corpus(tmp_path))
    system = _StubSystem(name="a2web", answer="body")
    suite = EvalSuite(
        corpus=corpus,
        systems=[system],
        judge=_MockJudge(),
        bench_judge=_MockBenchJudge(),
        output_dir=tmp_path / "out",
        provider="claude-code",
    )
    report = await suite.run()
    write_all(report)

    assert report.provider == "claude-code"
    assert report.rows and all(r.provider == "claude-code" for r in report.rows)

    manifest = json.loads((report.output_dir / "manifest.json").read_text())
    assert manifest["provider"] == "claude-code"
    results = json.loads((report.output_dir / "results.json").read_text())
    assert all(row["provider"] == "claude-code" for row in results["rows"])


@pytest.mark.asyncio
async def test_axis_isolation_runs_only_selected_axis(tmp_path: Path) -> None:
    """`axes={'quality'}` scores quality and skips the clarity + next_links LLM
    calls entirely — the per-axis isolation that keeps a spike cheap."""
    corpus = load_corpus(_corpus(tmp_path))
    system = _StubSystem(
        name="a2web",
        answer="body",
        next_links_block="anchor\turl\treason\nA\thttps://x\twhy",
    )

    class _CountingJudge(_MockJudge):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def score(self, *, task: str, criteria: list[str], answer: str) -> JudgeVerdict:
            self.calls += 1
            return await super().score(task=task, criteria=criteria, answer=answer)

    class _CountingBench(_MockBenchJudge):
        def __init__(self) -> None:
            super().__init__()
            self.clarity_calls = 0
            self.next_links_calls = 0

        async def score_clarity(self, *, task: str, answer: str) -> ClarityVerdict:
            self.clarity_calls += 1
            return await super().score_clarity(task=task, answer=answer)

        async def score_next_links(self, *, task: str, next_links: str) -> NextLinksVerdict:
            self.next_links_calls += 1
            return await super().score_next_links(task=task, next_links=next_links)

    judge = _CountingJudge()
    bench = _CountingBench()
    suite = EvalSuite(
        corpus=corpus,
        systems=[system],
        judge=judge,
        bench_judge=bench,
        output_dir=tmp_path / "out",
        axes=frozenset({"quality"}),
    )
    report = await suite.run()

    # Quality ran once per cell; clarity + next_links skipped entirely.
    assert judge.calls == len(corpus.entries)
    assert bench.clarity_calls == 0
    assert bench.next_links_calls == 0
    for row in report.rows:
        assert row.judge_overall == 4  # quality scored
        assert row.clarity_score is None  # clarity skipped
        assert row.next_links_score is None  # next_links skipped
