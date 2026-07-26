"""A `TRANSIENT (<change-id>)` marker must not outlive its change.

The convention: code that is provisional — kept only until a specific OpenSpec
change removes or replaces it — carries a `TRANSIENT (<change-id>)` marker in
its docstring. That marker is a *promise*: "this goes away when <change-id>
lands." A promise with no expiry is a rot seed. This guard is the expiry.

**Why this exact shape, and not a temporal-word ban.** Three false "design
questions" in the shelf sweep were authored from stale docstrings that
described a *finished* experiment in the present tense ("Deleted if it loses
the bake-off", "the bake-off's CDP candidate") long after the bake-off closed.
The tempting fix — ban words like "currently"/"will be" — is theater: it fires
on legitimate corrective narration ("a2kit *used to* own this, now this module
does", which PREVENTS confusion) and authors route around it with euphemism,
training docstrings to lie fluently. What is actually mechanizable is not the
word but the **unpinned lifecycle claim**: a `TRANSIENT` marker naming a change
that has already been archived. The archive directory is the exogenous witness
(the guard's belief is not the oracle — the filesystem's record of what shipped
is), which is why this is a real staleness floor and not another endogenous
guard. `DORMANT` (parked-but-retained code, e.g. the gated Camoufox launcher) is
deliberately NOT caught: it is an honest description of a current state, not a
broken promise.

Pairs with the witness rule in `docs/architecture/verification-provenance.md`:
this is one of the few places mechanism-A rot (stale prose) reduces to a
mechanism-B check (a floor on staleness), because "the change is archived" is a
fact on disk, not a judgement.
"""

from __future__ import annotations

import re

from tests.architecture._walk import REPO_ROOT, SRC_ROOT, walked_files

#: `TRANSIENT (some-change-id ...)` — capture the change-id (first token inside
#: the parens, before any space/section-marker/close-paren).
_TRANSIENT = re.compile(r"TRANSIENT\s*\(\s*([A-Za-z0-9][A-Za-z0-9._-]*)")

_ACTIVE_CHANGES = REPO_ROOT / "openspec" / "changes"
_ARCHIVED_CHANGES = _ACTIVE_CHANGES / "archive"


def _change_is_archived(change_id: str) -> bool:
    """True if `change_id` names a change that has been archived (i.e. shipped).

    Archived changes are dated (`2026-06-27-browser-backend-bakeoff`), so match
    by suffix/substring rather than exact name.
    """
    if not _ARCHIVED_CHANGES.is_dir():
        return False
    return any(change_id in p.name for p in _ARCHIVED_CHANGES.iterdir() if p.is_dir())


def _change_is_active(change_id: str) -> bool:
    """True if `change_id` names a currently-active (not-yet-archived) change."""
    candidate = _ACTIVE_CHANGES / change_id
    return candidate.is_dir()


def test_no_transient_marker_outlives_its_change() -> None:
    """Every `TRANSIENT (<change-id>)` names a change that is still active.

    Fails when the referenced change has been archived (the provisional code
    should have gone with it) or does not exist at all (a dangling promise).
    """
    offenders: list[str] = []
    for path in walked_files(SRC_ROOT, minimum=100):
        text = path.read_text(encoding="utf-8")
        for match in _TRANSIENT.finditer(text):
            change_id = match.group(1)
            rel = path.relative_to(REPO_ROOT)
            if _change_is_archived(change_id):
                offenders.append(
                    f"{rel}: TRANSIENT ({change_id}) — that change is ARCHIVED, "
                    "so the provisional code outlived it. Resolve or re-label."
                )
            elif not _change_is_active(change_id):
                offenders.append(
                    f"{rel}: TRANSIENT ({change_id}) — no active change by that "
                    "id (dangling promise). Point it at a real change or drop it."
                )
    assert not offenders, "Stale TRANSIENT markers found:\n" + "\n".join(offenders)


def test_guard_recognizes_an_archived_change() -> None:
    """Non-vacuity: prove the archive lookup actually resolves a real change.

    Without this, a broken `_ARCHIVED_CHANGES` path would make the guard above
    pass by finding nothing — the exact vacuous-green failure the witness rule
    warns about. Any archived change works as the fixture; the browser bake-off
    is a stable one.
    """
    assert _ARCHIVED_CHANGES.is_dir(), "archive directory moved — fix the path"
    archived = [p.name for p in _ARCHIVED_CHANGES.iterdir() if p.is_dir()]
    assert archived, "no archived changes found — the lookup would never fire"
    assert _change_is_archived("browser-backend-bakeoff"), (
        "expected the archived browser-backend-bakeoff change to resolve; "
        f"archive holds: {archived}"
    )
