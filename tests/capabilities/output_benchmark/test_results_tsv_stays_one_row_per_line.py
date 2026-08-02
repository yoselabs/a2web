"""`results.tsv` must keep one logical row on one physical line.

This file is piped into `awk` / `cut` / `jq`. Four of its columns are
LLM-authored prose (`quality_reason`, `clarity_reason`, `next_links_reason`,
`fetch_error`), so a judge returning a two-sentence rationale on separate lines
is enough to break that assumption.

`csv.DictWriter(delimiter="\t")` — what this writer used until 2026-08-02 — uses
QUOTE_MINIMAL: it emits such a cell QUOTED with the newline still literal
inside, so one row spans several lines and every line-oriented tool misparses,
silently and without an error anywhere. `lean_wire.encode_tsv` escapes instead
of quoting, which is exactly the behaviour `pyproject.toml` cites as the reason
lean-wire exists.
"""

from __future__ import annotations

from datetime import UTC, datetime

from a2web.llm_eval.report import _RESULTS_FIELDS, _write_results_tsv
from a2web.llm_eval.runner import EvalReport, EvalRow, QualityAxis

_MULTILINE_RATIONALE = "The answer names the price.\nIt also relays the source's own stated preference.\tTab too."


def _row() -> EvalRow:
    return EvalRow(
        slug="hazard",
        url="https://example.org/p",
        url_class="detail",
        task="what does it cost",
        system="a2web_detail",
        answer="it costs 100",
        fetch_latency_ms=120,
        fetch_cost_usd=0.0,
        fetch_prompt_tokens=10,
        fetch_completion_tokens=5,
        fetch_error=None,
        fetch_metadata={},
        quality=QualityAxis(reason=_MULTILINE_RATIONALE),
    )


def _write(tmp_path, rows: list[EvalRow]) -> list[str]:
    report = EvalReport(
        corpus_path="eval/corpus.yaml",
        systems=["a2web_detail"],
        rows=rows,
        output_dir=tmp_path,
        started_at=datetime(2026, 8, 2, tzinfo=UTC),
        ended_at=datetime(2026, 8, 2, tzinfo=UTC),
        judge_model="test-judge",
    )
    _write_results_tsv(report)
    return (tmp_path / "results.tsv").read_text(encoding="utf-8").splitlines()


def test_a_multiline_rationale_stays_on_one_line(tmp_path) -> None:
    """One row in, two lines out is the defect — and it is invisible in the file."""
    lines = _write(tmp_path, [_row()])

    assert len(lines) == 2, f"expected header + 1 row, got {len(lines)} lines — a cell broke the row across lines: {lines!r}"
    assert "\\n" in lines[1], "the newline must survive as an ESCAPE, not be dropped — the rationale is data"


def test_every_row_is_header_width(tmp_path) -> None:
    """A tab inside a cell must not shift every following column left."""
    lines = _write(tmp_path, [_row()])
    header = lines[0].split("\t")

    assert header == list(_RESULTS_FIELDS), "the declared column contract is the header"
    for line in lines[1:]:
        cells = line.split("\t")
        assert len(cells) == len(header), (
            f"row has {len(cells)} cells against {len(header)} columns — an embedded tab was not escaped: {line!r}"
        )


def test_a_declared_column_survives_rows_that_all_elide_it(tmp_path) -> None:
    """`columns=` is passed, not derived — a run where nothing errored still has the column.

    This is the case `lean_wire.derive_columns` kept the explicit parameter for:
    the union of the rows' keys is right when the rows define the schema, and
    wrong when a declared contract does.
    """
    lines = _write(tmp_path, [_row(), _row()])
    assert "fetch_error" in lines[0].split("\t"), "a declared column vanished because no row populated it"
