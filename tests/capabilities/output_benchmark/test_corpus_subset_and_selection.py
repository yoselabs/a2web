"""eval-results-json-and-subset: --only class filter + a selection-question case.

The `--only <class>` filter is a plain corpus-entry filter by `url_class`; these
tests pin the filter semantics and assert the real corpus carries a selection
("which is best?") case that exercises answer neutrality (ADR-0012).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from a2web.llm_eval.__main__ import _parse_args
from a2web.llm_eval.corpus import load_corpus

_CORPUS = load_corpus(Path("eval/corpus.yaml"))


def test_slug_filter_selects_single_item() -> None:
    target = _CORPUS.entries[0].slug
    subset = [e for e in _CORPUS.entries if e.slug in {target}]
    assert len(subset) == 1
    assert subset[0].slug == target


def test_parse_args_accepts_repeatable_slug_and_axis() -> None:
    ns = _parse_args(["--slug", "hn-front", "--slug", "foo", "--axis", "quality"])
    assert ns.slug == ["hn-front", "foo"]
    assert ns.axis == ["quality"]
    # Defaults: no isolation → both None (all items, all axes).
    assert _parse_args([]).slug is None
    assert _parse_args([]).axis is None


def test_parse_args_rejects_unknown_axis() -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--axis", "bogus"])


def test_only_listing_keeps_only_listing_cases() -> None:
    subset = [e for e in _CORPUS.entries if e.url_class == "listing"]
    assert subset  # there are listing cases
    assert all(e.url_class == "listing" for e in subset)
    assert len(subset) < len(_CORPUS.entries)  # a real subset


def test_unknown_class_matches_nothing() -> None:
    assert [e for e in _CORPUS.entries if e.url_class == "no-such-class"] == []


def test_corpus_has_a_selection_question_case() -> None:
    # A case whose task is a selection ("which is best / which should I pick").
    selection = [e for e in _CORPUS.entries if any(k in e.task.lower() for k in ("which is the best", "which of", "best one to"))]
    assert selection, "corpus should carry a selection-question case (answer-neutrality bench cell)"
    case = selection[0]
    assert case.url_class == "listing"
    # Its criteria reward presenting options / not crowning a single unqualified best.
    joined = " ".join(case.criteria).lower()
    assert "option" in joined or "criteria" in joined
    assert "not" in joined and "best" in joined
