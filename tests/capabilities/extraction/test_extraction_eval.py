"""Unit tests for the extraction-quality eval harness.

Covers the pure scoring primitives + corpus loader. The live runner
isn't tested here — it hits the real fetch pipeline and is exercised
via `python -m a2web.llm_eval.extraction_cli` against a real corpus.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from a2web.llm_eval.extraction import (
    ExtractionCorpusError,
    ExtractionResult,
    length_ratio,
    load_extraction_corpus,
    summarize,
    token_f1,
)

# --------------------------------------------------------------------- #
# token_f1
# --------------------------------------------------------------------- #


def test_token_f1_identical_strings_is_one() -> None:
    assert token_f1("hello world", "hello world") == 1.0


def test_token_f1_disjoint_is_zero() -> None:
    assert token_f1("hello world", "foo bar") == 0.0


def test_token_f1_partial_overlap() -> None:
    # 2 of 3 tokens overlap → precision=2/3, recall=2/3, F1=2/3
    score = token_f1("alpha beta gamma", "alpha beta delta")
    assert score == pytest.approx(2 / 3)


def test_token_f1_case_insensitive() -> None:
    assert token_f1("Hello WORLD", "hello world") == 1.0


def test_token_f1_empty_inputs_zero() -> None:
    assert token_f1("", "hello") == 0.0
    assert token_f1("hello", "") == 0.0
    assert token_f1("", "") == 0.0


def test_token_f1_markdown_punctuation_ignored() -> None:
    # # ** _ ` are not \w characters → ignored by tokenizer
    assert token_f1("# Title **bold**", "Title bold") == 1.0


# --------------------------------------------------------------------- #
# length_ratio
# --------------------------------------------------------------------- #


def test_length_ratio_equal() -> None:
    assert length_ratio("abc", "abc") == 1.0


def test_length_ratio_over_extraction() -> None:
    assert length_ratio("abcdef", "abc") == 2.0


def test_length_ratio_under_extraction() -> None:
    assert length_ratio("ab", "abcd") == 0.5


def test_length_ratio_empty_gold_is_zero() -> None:
    assert length_ratio("anything", "") == 0.0


# --------------------------------------------------------------------- #
# summarize
# --------------------------------------------------------------------- #


def _result(slug: str, f1: float, *, url_class: str = "") -> ExtractionResult:
    return ExtractionResult(
        slug=slug,
        url=f"https://example.com/{slug}",
        url_class=url_class,
        gold_chars=100,
        extracted_chars=100,
        token_f1=f1,
        length_ratio=1.0,
        fetch_ms=100,
        tier="raw",
        verdict="ok",
    )


def test_summarize_empty_results() -> None:
    summary = summarize([])
    assert summary.n == 0
    assert summary.mean_f1 == 0.0
    assert not summary.trips_reader_lm_threshold


def test_summarize_does_not_trip_when_all_pass() -> None:
    results = [_result(f"r{i}", 0.9) for i in range(10)]
    summary = summarize(results)
    assert summary.below_07_count == 0
    assert summary.below_07_pct == 0.0
    assert not summary.trips_reader_lm_threshold


def test_summarize_trips_at_10pct_default() -> None:
    # 1 of 10 below 0.7 → exactly 10% → trips (>=)
    results = [_result(f"r{i}", 0.9) for i in range(9)] + [_result("bad", 0.5)]
    summary = summarize(results)
    assert summary.below_07_count == 1
    assert summary.below_07_pct == pytest.approx(0.10)
    assert summary.trips_reader_lm_threshold


def test_summarize_per_class_slicing() -> None:
    results = [
        _result("a1", 0.9, url_class="docs"),
        _result("a2", 0.95, url_class="docs"),
        _result("b1", 0.5, url_class="forum"),
        _result("b2", 0.6, url_class="forum"),
    ]
    summary = summarize(results)
    assert summary.by_class["docs"]["mean_f1"] == pytest.approx(0.925)
    assert summary.by_class["docs"]["below_07_pct"] == 0.0
    assert summary.by_class["forum"]["mean_f1"] == pytest.approx(0.55)
    assert summary.by_class["forum"]["below_07_pct"] == 1.0


def test_summarize_threshold_and_miss_rate_overrides() -> None:
    # 5 of 10 below 0.8 — trip at 20% miss-rate, not at 60%
    results = [_result(f"r{i}", 0.9) for i in range(5)] + [_result(f"b{i}", 0.7) for i in range(5)]
    s_low = summarize(results, threshold=0.8, miss_rate=0.20)
    s_high = summarize(results, threshold=0.8, miss_rate=0.60)
    assert s_low.trips_reader_lm_threshold
    assert not s_high.trips_reader_lm_threshold


# --------------------------------------------------------------------- #
# corpus loader
# --------------------------------------------------------------------- #


def test_load_corpus_minimal(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(
        """
urls:
  - slug: a
    url: https://example.com/a
    class: docs
    gold_md: |
      # Title
      Body.
""".strip()
    )
    corpus = load_extraction_corpus(p)
    assert len(corpus) == 1
    assert corpus.entries[0].slug == "a"
    assert corpus.entries[0].url_class == "docs"
    assert "Body" in corpus.entries[0].gold_md


def test_load_corpus_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ExtractionCorpusError, match="not found"):
        load_extraction_corpus(tmp_path / "nope.yaml")


def test_load_corpus_empty_gold_rejected(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(
        """
urls:
  - slug: a
    url: https://example.com/a
    gold_md: "   "
""".strip()
    )
    with pytest.raises(ExtractionCorpusError, match="empty gold_md"):
        load_extraction_corpus(p)


def test_load_corpus_missing_field(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(
        """
urls:
  - slug: a
    url: https://example.com/a
""".strip()
    )
    with pytest.raises(ExtractionCorpusError, match="missing required field"):
        load_extraction_corpus(p)


def test_load_corpus_no_urls_list(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text("urls: []")
    with pytest.raises(ExtractionCorpusError, match="empty"):
        load_extraction_corpus(p)
