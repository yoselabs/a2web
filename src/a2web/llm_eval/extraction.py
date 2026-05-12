"""Extraction-quality eval harness — measure trafilatura+readability vs. gold.

The QA harness (`corpus.py` / `runner.py` / `systems.py`) measures whether
an agent can ANSWER QUESTIONS from a fetched page. This module measures
the upstream signal: does a2web's extraction pipeline produce markdown
that matches a hand-curated gold standard?

Trip condition for the Reader-LM v2 fallback (BACKLOG Reader-LM entry):
≥10% of URLs score below 0.7 token-F1 against gold. Drives the decision
on whether to add an LLM-based extraction tier behind trafilatura.

Corpus shape (YAML):

    urls:
      - slug: nyt-longform
        url: https://www.nytimes.com/2026/05/12/...
        class: longform_news
        gold_md: |
          # Headline

          Article body in clean markdown, hand-edited.
          Includes blockquotes, lists, the works.

`gold_md` is the only required content field. Everything else is
informational and carried through into result rows.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..fetcher import fetch as a2web_fetch
from ..state import AppState

# --------------------------------------------------------------------- #
# Corpus
# --------------------------------------------------------------------- #


@dataclass(slots=True)
class ExtractionEntry:
    slug: str
    url: str
    gold_md: str
    url_class: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractionCorpus:
    entries: list[ExtractionEntry]
    source_path: Path

    def __len__(self) -> int:
        return len(self.entries)


class ExtractionCorpusError(ValueError):
    """Raised when corpus YAML is missing required fields or malformed."""


def load_extraction_corpus(path: str | Path) -> ExtractionCorpus:
    """Load an extraction-quality corpus YAML."""
    p = Path(path)
    if not p.is_file():
        raise ExtractionCorpusError(f"corpus file not found: {p}")
    raw = yaml.safe_load(p.read_text()) or {}
    rows = raw.get("urls")
    if not isinstance(rows, list) or not rows:
        raise ExtractionCorpusError(f"corpus {p} has no `urls` list or it is empty")

    entries: list[ExtractionEntry] = []
    for i, raw_row in enumerate(rows):
        if not isinstance(raw_row, dict):
            raise ExtractionCorpusError(f"corpus {p} row {i} is not a mapping")
        row: dict[Any, Any] = raw_row
        try:
            slug = str(row["slug"])
            url = str(row["url"])
            gold_md = str(row["gold_md"])
        except KeyError as exc:
            raise ExtractionCorpusError(f"corpus {p} row {i} missing required field: {exc}") from exc
        if not gold_md.strip():
            raise ExtractionCorpusError(f"corpus {p} row {i} (slug={slug!r}) has empty gold_md")
        url_class = str(row.get("class") or "")
        extra: dict[str, Any] = {k: v for k, v in row.items() if k not in {"slug", "url", "gold_md", "class"}}
        entries.append(ExtractionEntry(slug=slug, url=url, gold_md=gold_md, url_class=url_class, extra=extra))
    return ExtractionCorpus(entries=entries, source_path=p)


# --------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------- #

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def token_f1(extracted: str, gold: str) -> float:
    """Bag-of-tokens F1 — precision x recall x 2 / (precision + recall).

    Standard SQuAD-style F1. Tokenization is conservative: \\w+ matches,
    lowercased. Markdown control chars don't tokenize so the score
    largely reflects content overlap, not formatting.
    """
    ext_tokens = _tokenize(extracted)
    gold_tokens = _tokenize(gold)
    if not ext_tokens or not gold_tokens:
        return 0.0

    ext_counter = Counter(ext_tokens)
    gold_counter = Counter(gold_tokens)
    overlap = sum((ext_counter & gold_counter).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(ext_tokens)
    recall = overlap / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def length_ratio(extracted: str, gold: str) -> float:
    """len(extracted) / len(gold). >1.0 = over-extraction; <1.0 = under."""
    if not gold:
        return 0.0
    return len(extracted) / len(gold)


# --------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------- #


@dataclass(slots=True)
class ExtractionResult:
    slug: str
    url: str
    url_class: str
    gold_chars: int
    extracted_chars: int
    token_f1: float
    length_ratio: float
    fetch_ms: int
    tier: str
    verdict: str
    error: str | None = None


async def run_extraction_eval(
    corpus: ExtractionCorpus,
    state: AppState,
    *,
    bypass_cache: bool = True,
) -> list[ExtractionResult]:
    """Fetch every corpus URL via a2web and score against gold_md.

    `bypass_cache=True` (default) — comparing the live pipeline against
    gold, not the cache. Flip to False to score what's already cached.
    """
    results: list[ExtractionResult] = []
    for entry in corpus.entries:
        t0 = time.perf_counter()
        try:
            response = await a2web_fetch(
                entry.url,
                state=state,
                include_links=False,
                debug=False,
                wrap_content=False,
            )
            fetch_ms = int((time.perf_counter() - t0) * 1000)
            extracted = response.content_md or ""
            results.append(
                ExtractionResult(
                    slug=entry.slug,
                    url=entry.url,
                    url_class=entry.url_class,
                    gold_chars=len(entry.gold_md),
                    extracted_chars=len(extracted),
                    token_f1=token_f1(extracted, entry.gold_md),
                    length_ratio=length_ratio(extracted, entry.gold_md),
                    fetch_ms=fetch_ms,
                    tier=response.tier,
                    verdict=response.status.value,
                    error=None if response.status.value == "ok" else response.diagnostics_summary,
                )
            )
        except Exception as exc:  # eval row must not abort the run
            fetch_ms = int((time.perf_counter() - t0) * 1000)
            results.append(
                ExtractionResult(
                    slug=entry.slug,
                    url=entry.url,
                    url_class=entry.url_class,
                    gold_chars=len(entry.gold_md),
                    extracted_chars=0,
                    token_f1=0.0,
                    length_ratio=0.0,
                    fetch_ms=fetch_ms,
                    tier="error",
                    verdict="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


# --------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------- #


@dataclass(slots=True)
class ExtractionSummary:
    n: int
    mean_f1: float
    median_f1: float
    p10_f1: float
    below_07_count: int
    below_07_pct: float
    by_class: dict[str, dict[str, float]]
    trips_reader_lm_threshold: bool


def summarize(results: list[ExtractionResult], *, threshold: float = 0.7, miss_rate: float = 0.10) -> ExtractionSummary:
    """Aggregate per-URL results into the Reader-LM trip-decision shape.

    Trip condition (BACKLOG default): ≥`miss_rate` of URLs scoring below
    `threshold` on token-F1 → recommend Reader-LM v2 fallback.
    """
    n = len(results)
    if n == 0:
        return ExtractionSummary(0, 0.0, 0.0, 0.0, 0, 0.0, {}, trips_reader_lm_threshold=False)

    f1s = sorted(r.token_f1 for r in results)
    mean_f1 = sum(f1s) / n
    median_f1 = f1s[n // 2]
    p10_f1 = f1s[max(0, int(n * 0.1) - 1)]
    below = [r for r in results if r.token_f1 < threshold]
    below_pct = len(below) / n

    by_class: dict[str, dict[str, float]] = {}
    seen_classes = {r.url_class for r in results if r.url_class}
    for cls in seen_classes:
        rows = [r for r in results if r.url_class == cls]
        by_class[cls] = {
            "n": float(len(rows)),
            "mean_f1": sum(r.token_f1 for r in rows) / len(rows),
            "below_07_pct": sum(1 for r in rows if r.token_f1 < threshold) / len(rows),
        }

    return ExtractionSummary(
        n=n,
        mean_f1=mean_f1,
        median_f1=median_f1,
        p10_f1=p10_f1,
        below_07_count=len(below),
        below_07_pct=below_pct,
        by_class=by_class,
        trips_reader_lm_threshold=below_pct >= miss_rate,
    )


def results_to_json(results: list[ExtractionResult], summary: ExtractionSummary) -> str:
    """Serialize results + summary to a single JSON blob for analysis."""
    return json.dumps(
        {
            "summary": asdict(summary),
            "results": [asdict(r) for r in results],
        },
        indent=2,
    )


__all__ = (
    "ExtractionCorpus",
    "ExtractionCorpusError",
    "ExtractionEntry",
    "ExtractionResult",
    "ExtractionSummary",
    "length_ratio",
    "load_extraction_corpus",
    "results_to_json",
    "run_extraction_eval",
    "summarize",
    "token_f1",
)
