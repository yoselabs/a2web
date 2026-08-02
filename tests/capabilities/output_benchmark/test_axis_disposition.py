"""An axis states whether it scored a cell, and why it did not.

The `next_links` axis scored ZERO cells from the day ADR-0015 shipped until this
change, and no test noticed. ADR-0015 folded `next_links` into `other_pages` on
the `AskResponse`; the reader kept asking the envelope for `next_links`, got
`None`, and `_score_next_links` returned on the branch that means *"this system
correctly produced no block"*. Verified against the last full run
(`eval/runs/2026-07-22_024912/`): `next_links_score` is `None` on 29 of 29
`a2web_extract` cells, while the stored envelope carries a populated
`other_pages` table.

**A test did cover the axis, and it could not have caught this.** The existing
`_StubSystem` builds its envelope by hand and writes the same key the reader
reads:

    envelope["next_links"] = self._next_links_block

Fake and reader agree with each other, and neither is the production model, so
the rename passed straight between them. That is why the guards here build a
REAL `AskResponse` and serialize it through the production `model_dump` — the
assertion's subject is the shipped model, so a future rename breaks it. A
hand-written fixture dict cannot witness a change to the thing it was copied
from.

Offline: no network, no LLM. These run in `make check`, which is the point —
the protection has to land before a live run is spent, not after.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from a2web.llm_eval import EvalSuite, SystemResult, load_corpus
from a2web.llm_eval.runner import AxisDisposition, _candidate_block
from a2web.models import AskResponse, OtherPage
from tests._helpers.llm_doubles import DoubleArm

from ._doubles import MockBenchJudge, MockJudge


def _real_query_envelope(*, with_candidates: bool) -> dict[str, object]:
    """A production `AskResponse` serialized exactly as the eval systems do.

    `A2WebExtract` records `ask_response.model_dump(mode="json")` in its result
    metadata, so this is byte-identical to what the harness reads in a live run.
    """
    pages = [
        OtherPage(url="https://example.com/page-2", reason="next page of results", kind="structural"),
        OtherPage(url="https://example.com/item-a", reason="detail for the top item", kind="drilldown"),
    ]
    response = AskResponse(
        url="https://example.com/listing",
        status="ok",
        tier="raw",
        confidence="high",
        answer="Top items: A, B, C.",
        other_pages=pages if with_candidates else [],
    )
    return response.model_dump(mode="json")


def test_the_real_envelope_carries_a_candidate_block() -> None:
    """Vacuity floor — the guard below must be looking at something.

    Without this, a serializer change that dropped `other_pages` entirely would
    make `test_candidate_block_is_read_from_the_query_envelope` pass by finding
    nothing in nothing.
    """
    envelope = _real_query_envelope(with_candidates=True)
    block = envelope.get("other_pages")
    assert isinstance(block, str) and block.strip(), (
        "the production AskResponse serializer produced no `other_pages` block for a "
        f"response built WITH candidates. Envelope keys: {sorted(envelope)}. Either the "
        "field was renamed again — in which case fix `_CANDIDATE_FIELD`, not this test — "
        "or the serializer stopped rendering it."
    )


def test_candidate_block_is_read_from_the_query_envelope() -> None:
    """The reader resolves the field the scored system actually emits."""
    envelope = _real_query_envelope(with_candidates=True)
    result = SystemResult(answer="Top items: A, B, C.", system="a2web_extract", latency_ms=5, metadata={"envelope": envelope})

    block = _candidate_block(result, system="a2web_extract")

    assert block is not None, (
        "the candidate-block reader found nothing in a REAL query envelope carrying "
        f"other_pages. Envelope keys: {sorted(envelope)}. This is the ADR-0015 failure: "
        "the reader is asking for a field name the envelope no longer uses."
    )
    assert "example.com/page-2" in block


def test_a_system_with_no_candidates_reads_as_absent_not_as_error() -> None:
    """An empty candidate set is a real answer, not a broken read."""
    envelope = _real_query_envelope(with_candidates=False)
    result = SystemResult(answer="Top items: A, B, C.", system="a2web_extract", latency_ms=5, metadata={"envelope": envelope})

    assert _candidate_block(result, system="a2web_extract") is None


def test_every_registered_system_declares_its_candidate_field() -> None:
    """A system joining the matrix cannot arrive with an unreadable axis."""
    from a2web.llm_eval.runner import _CANDIDATE_FIELD

    declared = set(_CANDIDATE_FIELD)
    assert len(declared) >= 2, f"the system->field table has {len(declared)} entries; it is not being read"
    # WebFetch has no structured envelope and is declared as carrying no
    # candidate field, rather than being silently absent from the table.
    assert "a2web_extract" in declared
    assert "a2web_detail" in declared
    assert "webfetch_baseline" in declared


def _listing_corpus(tmp_path: Path) -> Path:
    body = """
urls:
  - slug: listing
    url: https://example.com/listing
    class: listing
    next_links_expected: true
    task: List the top items.
    criteria: [count, titles]
"""
    path = tmp_path / "corpus.yaml"
    path.write_text(body)
    return path


class _EnvelopeSystem:
    """A system emitting a caller-supplied envelope under a caller-supplied name."""

    def __init__(self, *, name: str, envelope: dict[str, object]) -> None:
        self.name = name
        self._envelope = envelope

    async def fetch(self, *, url: str, ask: str) -> SystemResult:
        return SystemResult(answer="Top items: A, B, C.", system=self.name, latency_ms=5, metadata={"envelope": self._envelope})


@pytest.mark.asyncio
async def test_an_axis_requested_and_never_scored_is_reported_broken(tmp_path: Path) -> None:
    """Zero scores on a requested axis is a broken harness, not a result.

    Reproduces the shape of the real failure: the corpus asks for the axis, the
    system emits a candidate set, and the harness reads a field name that is not
    there. Today every such cell records `None` and the run reports a dash.
    """
    envelope = _real_query_envelope(with_candidates=True)
    # The field the harness once read, now absent — exactly the post-ADR-0015 state.
    assert "next_links" not in envelope
    system = _EnvelopeSystem(name="a2web_extract", envelope={k: v for k, v in envelope.items() if k != "other_pages"})

    suite = EvalSuite(
        corpus=load_corpus(_listing_corpus(tmp_path)),
        systems=[system],
        judge=MockJudge(),
        bench_judge=MockBenchJudge(),
        output_dir=tmp_path / "out",
    )
    report = await suite.run()

    assert "next_links" in report.broken_axes(), (
        "an axis requested on every cell and scored on none was not reported as broken. "
        "That is indistinguishable from an axis the corpus never asked for, which is how "
        "this axis stayed dead for five weeks."
    )


@pytest.mark.asyncio
async def test_a_scored_axis_is_not_reported_broken(tmp_path: Path) -> None:
    """The broken-axis check must be able to stay silent."""
    system = _EnvelopeSystem(name="a2web_extract", envelope=_real_query_envelope(with_candidates=True))

    suite = EvalSuite(
        corpus=load_corpus(_listing_corpus(tmp_path)),
        systems=[system],
        judge=MockJudge(),
        bench_judge=MockBenchJudge(),
        output_dir=tmp_path / "out",
    )
    report = await suite.run()

    assert report.broken_axes() == ()
    row = report.rows[0]
    assert row.next_links.disposition is AxisDisposition.SCORED
    assert row.next_links.score == 3


@pytest.mark.asyncio
async def test_an_axis_the_corpus_did_not_request_is_not_applicable(tmp_path: Path) -> None:
    """`not_applicable` and `unscored` are different records, not one sentinel."""
    body = """
urls:
  - slug: permalink
    url: https://example.com/article
    class: clean
    task: Summarize the article.
    criteria: [topic]
"""
    path = tmp_path / "corpus.yaml"
    path.write_text(body)
    system = _EnvelopeSystem(name="a2web_extract", envelope=_real_query_envelope(with_candidates=True))

    suite = EvalSuite(
        corpus=load_corpus(path),
        systems=[system],
        judge=MockJudge(),
        bench_judge=MockBenchJudge(),
        output_dir=tmp_path / "out",
    )
    report = await suite.run()

    row = report.rows[0]
    assert row.next_links.disposition is AxisDisposition.NOT_APPLICABLE
    assert row.next_links.score is None
    # A not-applicable cell is outside the axis denominator, so it cannot make
    # the axis look broken.
    assert report.broken_axes() == ()


@pytest.mark.asyncio
async def test_every_axis_renders_its_denominator(tmp_path: Path) -> None:
    """A mean is never printed without the number of cells behind it.

    `quality` and `clarity` used to render a bare mean beside an `n` column
    counting ALL rows, while `contract` and `next_links` rendered `12/14` and
    `4.0 (8)`. That inconsistency is the tell that this was an absent rule
    rather than an absent thought.
    """
    from a2web.llm_eval import write_all

    system = _EnvelopeSystem(name="a2web_extract", envelope=_real_query_envelope(with_candidates=True))
    suite = EvalSuite(
        corpus=load_corpus(_listing_corpus(tmp_path)),
        systems=[system],
        judge=MockJudge(),
        bench_judge=MockBenchJudge(),
        output_dir=tmp_path / "out",
    )
    report = await suite.run()
    write_all(report)

    axes_md = (report.output_dir / "axes.md").read_text()
    header = next(line for line in axes_md.splitlines() if line.startswith("| System |"))
    for axis in ("quality", "env tokens", "clarity", "next_links"):
        assert f"{axis} (n)" in header or f"{axis} ok" in header, (
            f"the axis table column for {axis!r} does not state its coverage. Header: {header}"
        )
    assert "## Axis coverage" in axes_md
    # The per-axis coverage table must name every axis, so no axis can go
    # unreported by being quietly left out of the loop.
    for axis in ("quality", "tokens", "contract", "clarity", "next_links"):
        assert f"| {axis} |" in axes_md, f"axis {axis!r} missing from the coverage table"


@pytest.mark.asyncio
async def test_a_broken_axis_still_leaves_complete_artifacts(tmp_path: Path) -> None:
    """A bench run is expensive; a broken axis must not cost the other axes."""
    from a2web.llm_eval import write_all

    envelope = _real_query_envelope(with_candidates=True)
    system = _EnvelopeSystem(name="a2web_extract", envelope={k: v for k, v in envelope.items() if k != "other_pages"})
    suite = EvalSuite(
        corpus=load_corpus(_listing_corpus(tmp_path)),
        systems=[system],
        judge=MockJudge(),
        bench_judge=MockBenchJudge(),
        output_dir=tmp_path / "out",
    )
    report = await suite.run()
    write_all(report)

    assert report.broken_axes() == ("next_links",)
    for artifact in ("results.tsv", "results.json", "manifest.json", "axes.md", "leaderboard.md", "cost.md"):
        assert (report.output_dir / artifact).exists(), f"{artifact} was not written for a run with a broken axis"
    assert "BROKEN AXES" in (report.output_dir / "axes.md").read_text()
    # The quality axis ran and is readable — the broken axis did not sink it.
    assert report.rows[0].quality.overall == 4


@pytest.mark.asyncio
async def test_the_manifest_states_the_cache_mode(tmp_path: Path) -> None:
    """A run that does not say how it was cached is not evidence of reproduction."""
    import json as _json

    from a2web.llm_eval import write_all

    for bypassed in (True, False):
        suite = EvalSuite(
            corpus=load_corpus(_listing_corpus(tmp_path)),
            systems=[_EnvelopeSystem(name="a2web_extract", envelope=_real_query_envelope(with_candidates=True))],
            judge=MockJudge(),
            bench_judge=MockBenchJudge(),
            output_dir=tmp_path / f"out-{bypassed}",
            extraction_cache_bypassed=bypassed,
        )
        report = await suite.run()
        write_all(report)
        manifest = _json.loads((report.output_dir / "manifest.json").read_text())
        assert manifest["extraction_cache_bypassed"] is bypassed


@pytest.mark.asyncio
async def test_the_bypass_flag_yields_an_extractor_with_no_cache(tmp_path: Path) -> None:
    """`--no-extraction-cache` must not read AND not write.

    Asserted against the built `Extractor`, not against the settings field —
    a settings assertion would restate the flag rather than test that anything
    honours it. An expiry-based bypass (ttl=0) would pass a settings check and
    still write, so the first cell of a run would poison the rest and a
    "bypassed" run would silently become cache-served partway through.
    """
    from async_scope import lazy

    from a2web.cache import SqliteResource
    from a2web.llm_resource import LlmExtractorResource
    from a2web.settings import AppSettings

    async def _build(*, enabled: bool):
        settings = AppSettings(extraction_cache_enabled=enabled, cache_dir=str(tmp_path))
        sqlite = SqliteResource(tmp_path / f"cache-{enabled}.db")
        resource = LlmExtractorResource(settings, sqlite, lazy(_CannedExtractProvider()))
        try:
            return await resource._ensure()
        finally:
            await sqlite.close()

    cached = await _build(enabled=True)
    bypassed = await _build(enabled=False)

    assert cached._cache is not None, "the default path lost its extraction cache — the guard below is now vacuous"
    assert bypassed._cache is None, (
        "extraction_cache_enabled=False still built a cache. A bypass that reads or writes "
        "makes 'reproduced N times' mean one observation reported N times."
    )


class _CannedExtractProvider:
    """Minimal Provider stand-in — the extractor is BUILT, never invoked.

    `OFF_CONTRACT` is the honest declaration and the claim is enforced by the
    `complete()` body below: this double asserts if anything ever calls it, so
    it cannot silently start standing in for prompt-dependent behaviour.
    """

    DOUBLES_ARM = DoubleArm.OFF_CONTRACT

    name = "canned"
    default_model = "canned-model"

    async def complete(self, **kwargs: object) -> object:  # pragma: no cover - never invoked
        raise AssertionError("the extractor should not be invoked by this test")
