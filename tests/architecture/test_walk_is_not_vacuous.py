"""The guard on the guards.

`_walk.walked_files` is the reason the other architecture tests cannot pass by
walking nothing. This file is the reason *it* cannot. If these three assertions
were ever deleted, every architecture test in this directory would quietly
become optional again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ._walk import SRC_ROOT, walked_files


def test_missing_root_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="root does not exist"):
        walked_files(tmp_path / "no-such-package", minimum=1)


def test_empty_tree_fails_instead_of_passing_vacuously(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(AssertionError, match="found 0 file"):
        walked_files(tmp_path / "empty", minimum=1)


def test_real_source_tree_clears_the_floor() -> None:
    """The floor is a floor, not a count — it must sit below the real tree."""
    assert len(walked_files(SRC_ROOT, minimum=80)) >= 80
