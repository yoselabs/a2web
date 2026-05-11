"""Corpus loader.

Reads the YAML corpus format used by `benchmarks/vs-webfetch/.../corpus.yaml`:

    urls:
      - slug: hn-front
        url: https://news.ycombinator.com/
        class: A_clean
        task: "List the top 5 stories..."
        needs: [content+links]
        criteria:
          - "Identifies 5 stories from the front page"
          - "..."

Validation is intentionally minimal — slug + url + task + criteria must be
present and non-empty. Everything else is informational (carried through
into the result rows for downstream analysis).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class CorpusEntry:
    slug: str
    url: str
    task: str
    criteria: list[str]
    url_class: str = ""
    needs: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Corpus:
    entries: list[CorpusEntry]
    source_path: Path

    def __len__(self) -> int:
        return len(self.entries)


class CorpusError(ValueError):
    """Raised when corpus YAML is missing required fields or malformed."""


def load_corpus(path: str | Path) -> Corpus:
    """Load a corpus YAML file. Raises CorpusError on shape problems."""
    p = Path(path)
    if not p.is_file():
        raise CorpusError(f"corpus file not found: {p}")

    raw = yaml.safe_load(p.read_text()) or {}
    rows = raw.get("urls")
    if not isinstance(rows, list) or not rows:
        raise CorpusError(f"corpus {p} has no `urls` list or it is empty")

    entries: list[CorpusEntry] = []
    for i, raw_row in enumerate(rows):
        if not isinstance(raw_row, dict):
            raise CorpusError(f"corpus {p} row {i} is not a mapping")
        # yaml.safe_load returns a generic dict; carry as Any-keyed for ty.
        row: dict[Any, Any] = raw_row
        try:
            slug = str(row["slug"])
            url = str(row["url"])
            task = str(row["task"])
            criteria_raw = row["criteria"]
        except KeyError as exc:
            raise CorpusError(
                f"corpus {p} row {i} missing required field: {exc}"
            ) from exc
        if not isinstance(criteria_raw, list) or not criteria_raw:
            raise CorpusError(
                f"corpus {p} row {i} (slug={slug!r}) has empty/invalid criteria"
            )
        criteria = [str(c) for c in criteria_raw]
        url_class = str(row.get("class") or "")
        needs_raw = row.get("needs") or []
        needs = [str(n) for n in needs_raw]
        extra: dict[str, Any] = {
            k: v
            for k, v in row.items()
            if k not in {"slug", "url", "task", "criteria", "class", "needs"}
        }
        entries.append(
            CorpusEntry(
                slug=slug,
                url=url,
                task=task,
                criteria=criteria,
                url_class=url_class,
                needs=needs,
                extra=extra,
            )
        )

    return Corpus(entries=entries, source_path=p)


__all__ = ["Corpus", "CorpusEntry", "CorpusError", "load_corpus"]
