"""The shared source-tree walker for architecture tests — and its self-check.

Every architecture test in this directory has the same shape: walk a root,
parse each `.py`, collect offenders, assert the list is empty. That shape has
a silent failure mode — **if the walk yields nothing, the offender list is
also empty, and the test reports green.** A mistyped root, a moved package,
or a `parents[2]` that stops pointing at the repo turns a guard into a
decoration without ever going red.

Measured on 2026-07-22: 30 of 32 architecture tests passed against an *empty*
source tree.

So the walk asserts its own preconditions. `minimum` is a floor, not a count —
set it well below the current population so ordinary deletions do not trip it,
and well above zero so a broken root does. It exists to catch "the walk found
nothing like what it expected", never to freeze the file count.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "a2web"


def walked_files(root: Path, *, minimum: int) -> list[Path]:
    """Return every `.py` under `root`, asserting the walk is not vacuous."""
    assert root.is_dir(), (
        f"architecture-test root does not exist: {root}\n"
        "The guard cannot walk a tree that isn't there — fix the path, do not "
        "let the test pass by finding nothing."
    )
    paths = sorted(root.rglob("*.py"))
    assert len(paths) >= minimum, (
        f"architecture-test walk over {root} found {len(paths)} file(s), "
        f"expected at least {minimum}.\n"
        "Either the root moved (fix the path) or the tree genuinely shrank "
        "below the floor (lower `minimum` deliberately). An empty walk makes "
        "this guard pass vacuously."
    )
    return paths
