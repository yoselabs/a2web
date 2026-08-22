"""Direct unit tests for `eval._capture.corpus`'s `CorpusError` guard clauses.

Every existing test that touches `load_case`/`load_corpus` does so indirectly,
through a real fixture corpus on disk — none of them ever hits a malformed
case and exercises a guard clause itself. These build minimal case
directories by hand under `tmp_path` instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval._capture.corpus import CorpusError, load_case, load_corpus


def test_load_case_missing_case_yaml(tmp_path: Path) -> None:
    case_dir = tmp_path / "no-case-yaml"
    case_dir.mkdir()

    with pytest.raises(CorpusError, match="has no case\\.yaml"):
        load_case(case_dir)


def test_load_case_missing_slug_field(tmp_path: Path) -> None:
    case_dir = tmp_path / "missing-slug"
    case_dir.mkdir()
    (case_dir / "case.yaml").write_text("url: https://example.com\n")

    with pytest.raises(CorpusError, match="missing required field"):
        load_case(case_dir)


def test_load_case_missing_url_field(tmp_path: Path) -> None:
    case_dir = tmp_path / "missing-url"
    case_dir.mkdir()
    (case_dir / "case.yaml").write_text("slug: example\n")

    with pytest.raises(CorpusError, match="missing required field"):
        load_case(case_dir)


def test_load_case_non_mapping_case_yaml(tmp_path: Path) -> None:
    case_dir = tmp_path / "list-case-yaml"
    case_dir.mkdir()
    (case_dir / "case.yaml").write_text("- one\n- two\n")

    with pytest.raises(CorpusError, match="is not a mapping"):
        load_case(case_dir)


def test_load_corpus_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(CorpusError, match="corpus dir not found"):
        load_corpus(missing)
