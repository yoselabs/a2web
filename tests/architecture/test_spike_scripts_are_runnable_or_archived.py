"""A spike script either still runs, or says out loud that it doesn't.

Measured 2026-07-27: **18 of 19** spike scripts in this repo could not import.
The a2kit sunset took nine of them (`a2kit.ldd`, `a2kit.testing`), and the shelf
promotions took the rest (`packages/llm_extract/providers`, `packages/browser_pool`,
`packages/cookie_store` — each moved out from under a hardcoded import path).
Nothing went red, because no test imports a spike and a spike is only ever run by
hand, months apart.

That is tolerable for a one-shot experiment whose real output is the frozen
`*_output.md` beside it. It is NOT tolerable for the three probes under
`docs/history/spikes/`, because **ADR-0011 names them as the instruments of its
own re-evaluation triggers** ("Probe scripts: `reddit_json_cookie_spike.py`").
An ADR that says "re-run this to reopen the decision" and points at a script
that cannot import has quietly become un-reopenable — the decision is frozen by
bit-rot rather than by evidence, which is the opposite of what the trigger was
written to guarantee.

So the rule is not "every spike must work". It is **every spike must be honest
about whether it works**:

  * imports cleanly → live, and this guard keeps it that way;
  * carries a `# SPIKE-ARCHIVED: <reason>` line → a frozen artifact, read for
    its recorded output, not expected to run.

Marking a script archived is a deliberate, reviewable sentence in a diff. Rot is
not. Note the asymmetry this encodes: an archived script that happens to import
is fine, but a live script that stops importing is a failure — because the
damage is a trigger you cannot pull, not a file that is out of date.

**Scope limit, stated honestly.** This resolves imports against the current dev
environment, so a spike whose dependency lives in an uninstalled optional extra
will read as broken and be pushed toward a marker it may not deserve. Every
third-party import across the current population resolves, so the situation is
hypothetical today; if it stops being hypothetical, narrow the check to
first-party modules rather than deleting it.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from ._walk import REPO_ROOT

#: Both spike homes. `eval/spikes/` is the working corpus (mostly one-shot);
#: `docs/history/spikes/` is the ADR-cited set.
_SPIKE_DIRS: tuple[Path, ...] = (
    REPO_ROOT / "eval" / "spikes",
    REPO_ROOT / "docs" / "history" / "spikes",
)

#: The opt-out. Must carry a reason — a bare marker would be a mute silencer.
_ARCHIVED_MARKER = "# SPIKE-ARCHIVED:"

#: Floor for the walk. Population is 19; well below it so deleting a stale spike
#: does not trip the guard, well above zero so a moved directory does.
_MIN_SPIKES = 12


def _spike_files() -> list[Path]:
    found = [p for d in _SPIKE_DIRS if d.is_dir() for p in sorted(d.glob("*.py"))]
    assert len(found) >= _MIN_SPIKES, (
        f"spike walk found {len(found)} file(s), expected at least {_MIN_SPIKES}. "
        "Either a spike directory moved (fix the path) or the population genuinely "
        "shrank below the floor (lower it deliberately). An empty walk makes this "
        "guard pass vacuously."
    )
    return found


def _unresolvable_imports(path: Path) -> list[str]:
    """Modules `path` imports that cannot be resolved.

    Parses rather than imports: importing a spike would *run* it, and several
    make live network calls and spend LLM quota at module scope.
    """
    broken: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue  # relative import — no package context to resolve against
            try:
                module = importlib.import_module(node.module)
            except Exception:
                broken.append(f"{node.module} (module gone)")
                continue
            broken += [f"{node.module}.{a.name} (name gone)" for a in node.names if not hasattr(module, a.name)]
        elif isinstance(node, ast.Import):
            for alias in node.names:
                try:
                    importlib.import_module(alias.name)
                except Exception:
                    broken.append(f"{alias.name} (module gone)")
    return broken


def test_the_walk_is_not_vacuous() -> None:
    """A guard that found no spikes is indistinguishable from a passing one."""
    _spike_files()


def test_every_spike_either_imports_or_is_marked_archived() -> None:
    offenders: list[str] = []
    for path in _spike_files():
        if _ARCHIVED_MARKER in path.read_text(encoding="utf-8"):
            continue
        broken = _unresolvable_imports(path)
        if broken:
            rel = path.relative_to(REPO_ROOT)
            offenders.append(f"  {rel}\n" + "".join(f"      {b}\n" for b in sorted(set(broken))))

    assert not offenders, (
        "spike scripts that no longer import and are not marked archived:\n\n"
        + "".join(offenders)
        + "\nEither repair the import (usually a module that moved to the shelf — "
        "check what the promotion renamed it to), or add a line\n\n"
        f"    {_ARCHIVED_MARKER} <why this is a frozen artifact, not a live tool>\n\n"
        "Prefer repair for anything an ADR cites as a re-evaluation trigger: a "
        "probe that cannot run makes its decision un-reopenable."
    )


def test_the_adr_cited_probes_are_live_not_archived() -> None:
    """`docs/history/spikes/` is the cited set — archiving it defeats the point.

    Without this, the previous test is satisfiable by marking every probe
    archived, which would convert a red build into exactly the silent
    un-reopenability the marker exists to make visible.
    """
    cited = REPO_ROOT / "docs" / "history" / "spikes"
    probes = sorted(cited.glob("*.py"))
    assert len(probes) >= 3, f"expected the ADR-cited probe set under {cited}, found {len(probes)}"

    for path in probes:
        assert _ARCHIVED_MARKER not in path.read_text(encoding="utf-8"), (
            f"{path.relative_to(REPO_ROOT)} is marked archived, but ADR-0011 cites this "
            "directory as the instrument set for its re-evaluation triggers. Repair it "
            "instead, or update the ADR to stop promising a probe that no longer runs."
        )
        assert not _unresolvable_imports(path), f"{path.relative_to(REPO_ROOT)} cannot import: {_unresolvable_imports(path)}"
