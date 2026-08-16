"""Every declared `FetchStatus` member is emitted by some code path.

`FetchStatus` shipped three members — `ok`, `failed`, `partial` — and only ever
produced two. `partial` sat on a live wire contract for the whole life of the
enum with nothing able to emit it, so a calling agent reading the tool contract
saw a state it could never receive, and any consumer branching on it held code
that could never run and no way to find out.

ADR-0019 had already written the field as `(ok | failed)` — *"a coarse, lossy
collapse of `final_verdict` down to one bit"* — while the code kept declaring a
third. A prose decision does not delete a member; this does.

Deleting `partial` fixes today. This guard is the other half (ADR-0001,
structural prevention over vigilance): a member added for symmetry, or reserved
for a design nobody committed to, fails the suite instead of reaching the wire.

The sibling vocabulary already works this way —
`test_every_hint_code_has_a_factory.py` asserts every declared hint code is built
by something. This is that census applied to the status enum.

**A comparison is not a producer.** `status == FetchStatus.partial` is precisely
the dead consumer branch an unproduced member creates, so counting it would make
the guard vouch for the defect it exists to catch.
"""

from __future__ import annotations

import ast

import pytest

from a2web.models import FetchStatus

from ._walk import SRC_ROOT, walked_files

#: Well below the 145 files under `src/a2web` — a floor to catch a broken walk,
#: not a count to freeze (see `_walk.py`).
_MINIMUM_SOURCE_FILES = 60

_ENUM = "FetchStatus"


def _producers(source: str) -> set[str]:
    """Members of `FetchStatus` this source *emits*, ignoring comparisons.

    A member counts when a `FetchStatus.<member>` access appears inside the value
    of an assignment or a return. Anything reached through a `Compare` is dropped
    first, so `is_ok = fr.status == FetchStatus.ok` reads a status rather than
    producing one.
    """
    tree = ast.parse(source)

    compared: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            compared.update(id(inner) for inner in ast.walk(node))

    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign | ast.AnnAssign | ast.Return):
            continue
        value = node.value
        if value is None:
            continue
        for inner in ast.walk(value):
            if id(inner) in compared:
                continue
            if isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name) and inner.value.id == _ENUM:
                found.add(inner.attr)
    return found


def _producers_in_src() -> set[str]:
    found: set[str] = set()
    for path in walked_files(SRC_ROOT, minimum=_MINIMUM_SOURCE_FILES):
        found |= _producers(path.read_text(encoding="utf-8"))
    return found


def test_the_census_is_not_vacuous() -> None:
    """A walk that recognised no producer at all would pass every check below."""
    found = _producers_in_src()
    assert found, f"found no `{_ENUM}.<member>` producer anywhere in src/ — the walk is not reading the tree"
    assert len(FetchStatus) >= 2, f"{_ENUM} declares {len(FetchStatus)} member(s) — the enum is not being read"


@pytest.mark.protects("spec:app-composition", "Requirement: Closed-enum status, confidence, and cache state")
def test_every_declared_status_has_a_producer() -> None:
    """THE regression. `partial` was declared for the enum's whole life and never emitted."""
    produced = _producers_in_src()
    missing = sorted(member.value for member in FetchStatus if member.name not in produced)
    assert not missing, (
        f"declared `{_ENUM}` members that no code path in src/ emits:\n"
        + "".join(f"  {member}\n" for member in missing)
        + "\nAn unproduced member is a state the tool contract promises a caller "
        "and can never deliver, so every consumer branch on it is dead on "
        "arrival. Give it a producer, or remove it from the enum."
    )


def test_a_comparison_alone_does_not_count_as_a_producer() -> None:
    """The distinction the guard turns on, asserted rather than assumed.

    Without this, a walk that counted comparison sites would report `partial`
    produced by the very dead branch its absence creates, and the guard above
    would have been green throughout the defect it exists to catch.
    """
    emits = "def f(v):\n    status = FetchStatus.ok\n    return status\n"
    compares = "def g(r):\n    is_gone = r.status == FetchStatus.partial\n    return is_gone\n"

    assert _producers(emits) == {"ok"}
    assert _producers(compares) == set()
    assert _producers(emits + compares) == {"ok"}


def test_a_return_counts_as_a_producer() -> None:
    """A member emitted only by a bare `return` is produced, and must not be flagged."""
    assert _producers("def h():\n    return FetchStatus.failed\n") == {"failed"}
