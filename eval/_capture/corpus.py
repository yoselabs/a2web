"""On-disk replay-corpus loader.

A corpus is a directory of cases:

    eval/corpus/<corpus>/<case>/
        case.yaml               # question, url, failure class, tags, tier path
        inputs/
            raw.http            # frozen HTTP egress (URL-keyed; may hold many)
            rendered.html       # frozen browser-rendered DOM (when frozen)
            llm/<key>.json      # recorded LLM provider responses (when frozen)
        baseline/
            contract.json       # asserted deterministic shape
            answer.md           # reference answer for LLM-judged axes
        meta.yaml               # per-layer capture timestamp, hashes, sizes

`case.yaml` extends the bench corpus entry shape (slug/url/class/task/
needs/criteria/next_links_expected) with `question`, `failure_class`
(A/B/C — see README), and `tags` (commerce/js/spa, which drive the
eager browser-freeze policy).

`inputs/` is a snapshot of the world and MAY drift; `baseline/` is what
the substrate asserts. They are loaded as distinct objects so the
diff/bless flow can tell a code-driven change from a site-driven one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from http_fetch import FetchOutcome

from .cassette import parse_exchanges

# Failure-class taxonomy (the `failure_class` field). Full prose in
# eval/_capture/README.md.
FAILURE_CLASSES = frozenset({"A", "B", "C"})

# Tags that make capture eagerly freeze the browser-rendered DOM even when
# the live run did not escalate to the browser tier (these classes escalate).
EAGER_BROWSER_TAGS = frozenset({"commerce", "js", "spa"})


class CorpusError(ValueError):
    """Missing or malformed corpus case."""


@dataclass(slots=True)
class CaseInputs:
    """Frozen world for a case — the egress captures. MAY drift."""

    http: dict[str, FetchOutcome] = field(default_factory=dict)
    rendered_html: str | None = None
    llm: dict[str, dict[str, Any]] = field(default_factory=dict)

    def frozen_tiers(self) -> set[str]:
        """Coarse set of tiers this cassette can serve, for gap diagnostics."""
        tiers: set[str] = set()
        if self.http:
            tiers |= {"raw", "jina", "archive", "site_handler"}
        if self.rendered_html is not None:
            tiers.add("browser")
        return tiers


@dataclass(slots=True)
class CaseBaseline:
    """What the substrate asserts. Updated only via an explicit bless."""

    contract: dict[str, Any] = field(default_factory=dict)
    answer: str | None = None


@dataclass(slots=True)
class ReplayCase:
    slug: str
    url: str
    question: str | None
    failure_class: str
    tags: frozenset[str]
    corpus: str
    path: Path
    inputs: CaseInputs
    baseline: CaseBaseline
    meta: dict[str, Any] = field(default_factory=dict)
    spec: dict[str, Any] = field(default_factory=dict)

    @property
    def eager_browser(self) -> bool:
        return bool(self.tags & EAGER_BROWSER_TAGS)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text()) or {}
    if not isinstance(loaded, dict):
        raise CorpusError(f"{path} is not a mapping")
    return loaded


def _load_inputs(inputs_dir: Path) -> CaseInputs:
    http: dict[str, FetchOutcome] = {}
    for http_file in sorted(inputs_dir.glob("*.http")):
        http.update(parse_exchanges(http_file.read_text()))

    rendered_path = inputs_dir / "rendered.html"
    rendered_html = rendered_path.read_text() if rendered_path.is_file() else None

    llm: dict[str, dict[str, Any]] = {}
    llm_dir = inputs_dir / "llm"
    if llm_dir.is_dir():
        for llm_file in sorted(llm_dir.glob("*.json")):
            llm[llm_file.stem] = json.loads(llm_file.read_text())

    return CaseInputs(http=http, rendered_html=rendered_html, llm=llm)


def _load_baseline(baseline_dir: Path) -> CaseBaseline:
    contract_path = baseline_dir / "contract.json"
    contract = json.loads(contract_path.read_text()) if contract_path.is_file() else {}
    answer_path = baseline_dir / "answer.md"
    answer = answer_path.read_text() if answer_path.is_file() else None
    return CaseBaseline(contract=contract, answer=answer)


def load_case(case_dir: Path, *, corpus: str = "") -> ReplayCase:
    """Load one case directory into a `ReplayCase`."""
    case_dir = Path(case_dir)
    spec = _read_yaml(case_dir / "case.yaml")
    if not spec:
        raise CorpusError(f"case {case_dir} has no case.yaml")
    try:
        slug = str(spec["slug"])
        url = str(spec["url"])
    except KeyError as exc:
        raise CorpusError(f"case {case_dir} missing required field: {exc}") from exc

    failure_class = str(spec.get("failure_class") or spec.get("class") or "").upper()
    tags = frozenset(str(t) for t in (spec.get("tags") or []))
    question = spec.get("question")

    return ReplayCase(
        slug=slug,
        url=url,
        question=str(question) if question is not None else None,
        failure_class=failure_class,
        tags=tags,
        corpus=corpus,
        path=case_dir,
        inputs=_load_inputs(case_dir / "inputs"),
        baseline=_load_baseline(case_dir / "baseline"),
        meta=_read_yaml(case_dir / "meta.yaml"),
        spec=spec,
    )


def load_corpus(corpus_dir: Path) -> list[ReplayCase]:
    """Load every case under a corpus directory, sorted by slug."""
    corpus_dir = Path(corpus_dir)
    if not corpus_dir.is_dir():
        raise CorpusError(f"corpus dir not found: {corpus_dir}")
    cases = [
        load_case(child, corpus=corpus_dir.name)
        for child in sorted(corpus_dir.iterdir())
        if child.is_dir() and (child / "case.yaml").is_file()
    ]
    return cases
