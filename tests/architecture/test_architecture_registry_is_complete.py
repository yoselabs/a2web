"""Every architecture guard appears in the rules registry.

`docs/architecture/README.md` listed **10 of 34** guards. Not neglect — the
documented "adding a rule = write a test" workflow had no step that said to
register it, so every new guard silently widened the gap. A reader consulting
that file for "what is enforced here" got a wrong answer delivered with
authority, which is the same failure class as a guard that reads green: the
artifact reports coverage it does not have.

Adding the missing entries by hand only resets the clock. Completeness is a
property of the artifact — a file either is named in the document or is not —
so it is mechanizable, and mechanizing it is strictly better than adding a step
to a workflow that people follow from memory.
"""

from __future__ import annotations

from pathlib import Path

from ._walk import REPO_ROOT

_GUARD_DIR = Path(__file__).resolve().parent
_REGISTRY = REPO_ROOT / "docs" / "architecture" / "README.md"

#: Below the current population (34), far above zero.
_MIN_GUARDS = 20


def _guard_files() -> list[Path]:
    return sorted(_GUARD_DIR.glob("test_*.py"))


def test_every_guard_is_registered() -> None:
    guards = _guard_files()
    assert len(guards) >= _MIN_GUARDS, (
        f"walked {len(guards)} guard file(s), expected at least {_MIN_GUARDS} — "
        "the directory moved and this check is inspecting nothing."
    )
    assert _REGISTRY.exists(), f"the rules registry is missing: {_REGISTRY}"

    registry = _REGISTRY.read_text(encoding="utf-8")
    unregistered = sorted(p.name for p in guards if p.name not in registry)

    assert not unregistered, (
        "architecture guard(s) missing from docs/architecture/README.md:\n"
        + "".join(f"  {name}\n" for name in unregistered)
        + "\nA registry that lists some of the guards is worse than none: a reader "
        "takes it as the enforced set. Add a one-line entry — the guard's own "
        "docstring summary is usually the right text."
    )


def test_the_registry_does_not_cite_guards_that_are_gone() -> None:
    """The other direction. A listed-but-deleted guard reads as coverage too.

    This is how `test_no_lambdas_in_app_provide.py` (subject died with a2kit)
    and `test_transient_markers_not_stale.py` (retired) stayed in the document
    after their files were gone.
    """
    import re

    registry = _REGISTRY.read_text(encoding="utf-8")
    live = {p.name for p in _guard_files()}

    cited = set(re.findall(r"tests/architecture/(test_[a-z0-9_]+\.py)", registry))
    assert len(cited) >= _MIN_GUARDS, f"non-vacuous: parsed only {len(cited)} citations from the registry"

    # A citation may survive its file ONLY when marked historical on the same line.
    ghosts = []
    for name in sorted(cited - live):
        for line in registry.splitlines():
            if name in line and not ("retired" in line or "withdrawn" in line or "<!-- gone -->" in line):
                ghosts.append(name)
                break

    assert not ghosts, (
        "the registry cites guard file(s) that no longer exist:\n"
        + "".join(f"  {name}\n" for name in ghosts)
        + "\nMark the entry retired/withdrawn with the reason, or remove it. A live-looking "
        "citation to a deleted guard is exactly the rot this change exists to close."
    )
