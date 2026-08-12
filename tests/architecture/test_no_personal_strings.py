"""The shipping tree carries no operator identifiers.

This repo is public. Personal paths, handles, and private host names leak back in
the ordinary way — a debugging note pasted into an ADR, an absolute path in a
Makefile comment, a `~/.claude.json` snippet in the docs. Each one is individually
harmless and none of them survives review reliably, because nobody is looking for
them; they arrive as a side effect of writing about something else.

So this is a floor, not a review step. It scans the shipping tree on every
`make check` and fails on reappearance.

**Scope is narrow on purpose.** Two exclusions carry their reasons:

  * `openspec/changes/**` — planning documents and the archived historical
    record. Rewriting shipped history to look tidier is the opposite of an honest
    engineering log, and a change that *proposes removing* an identifier has to
    be able to name it. `openspec/specs/**`, the durable spec, IS scanned.
  * eval and benchmark FIXTURES — frozen copies of real web pages. A denylist
    term can legitimately appear as page content (a cited academic author named
    Shen, a GitHub username), and editing a fixture to satisfy a lint corrupts
    the thing under test. This is why the denylist below is composed of
    *identifiers* (`iorlas`, a private FQDN, `/Users/`) rather than of names: a
    bare first name or surname cannot be distinguished from page content, so
    banning one would force exactly that corruption.
"""

from __future__ import annotations

from pathlib import Path

from ._walk import REPO_ROOT

#: Substrings that identify the operator or their machine. Every entry must be
#: unambiguous — see the module docstring on why names are NOT in this list.
_DENIED: tuple[str, ...] = (
    "iorlas",
    "mcp.shen.iorlas.net",
    "38.242.156.243",  # the operator's egress IP — cited in two ADRs and the bd archive
    "/Users/",
)

#: Text-ish files worth scanning. Binary and lockfiles are excluded by extension
#: rather than by sniffing, so the walk stays cheap and predictable.
_SUFFIXES: frozenset[str] = frozenset({".py", ".md", ".toml", ".yaml", ".yml", ".json", ".jsonl", ".sh", ".cfg", ".txt", ""})

#: Path prefixes excluded from the scan, each for a reason stated in the module
#: docstring. Note what is NOT here: `.venv`, caches, and build output need no
#: entry, because the scan reads the git index rather than the filesystem — what
#: git tracks is exactly what is distributed, so untracked local cruft (a
#: `.hypothesis` cache carrying absolute paths) can never make this red.
_SKIP_PREFIXES: tuple[str, ...] = (
    "openspec/changes/",  # planning + the archived historical record — see docstring
    "benchmarks/",  # frozen run artifacts over real pages
    "eval/corpus/",  # frozen page captures
)

#: The walk must find at least this many files. Well below the current population
#: (~500) so ordinary deletions do not trip it, and well above zero so a broken
#: root does. Without this the guard passes by scanning nothing — the exact
#: failure that let 30 of 32 architecture tests pass against an empty tree.
_MIN_FILES = 150


def _shipping_files() -> list[Path]:
    """Every tracked, text-ish file outside the documented exclusions.

    Reads the git index, not the filesystem: the question this guard asks is
    "what do we distribute", and git already answers it exactly.
    """
    import subprocess

    listing = subprocess.run(  # noqa: S603 - fixed argv, no shell, repo-local
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],  # noqa: S607
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    out: list[Path] = []
    for rel in listing.split("\0"):
        if not rel or rel.startswith(_SKIP_PREFIXES):
            continue
        path = REPO_ROOT / rel
        if path.suffix not in _SUFFIXES or not path.is_file():
            continue
        out.append(path)
    return sorted(out)


def test_the_walk_is_not_vacuous() -> None:
    """A guard that scanned nothing is indistinguishable from a passing one."""
    found = _shipping_files()
    assert len(found) >= _MIN_FILES, (
        f"personal-string scan found {len(found)} file(s), expected at least {_MIN_FILES}. "
        "Either the root moved (fix it) or the exclusions grew too broad. Do NOT "
        "lower the floor to make this pass."
    )


def test_no_personal_identifiers_in_the_shipping_tree() -> None:
    offenders: list[str] = []
    for path in _shipping_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable — nothing a human wrote a path into
        rel = path.relative_to(REPO_ROOT)
        if rel == Path(__file__).relative_to(REPO_ROOT):
            continue  # this file necessarily contains the denylist
        for term in _DENIED:
            if term in text:
                line = next((i for i, ln in enumerate(text.splitlines(), 1) if term in ln), 0)
                offenders.append(f"{rel}:{line}: contains {term!r}")

    assert not offenders, (
        "operator identifiers found in the shipping tree:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n\nReplace with a generic placeholder (`$HOME`, `<repo>`, `<your-gateway>`). "
        "If the match is genuine page content inside a frozen fixture, exclude that "
        "fixture directory instead of editing the capture."
    )


def test_the_denylist_actually_matches_something() -> None:
    """The check must be able to FAIL, not merely to pass.

    A denylist of terms that can never match is a decoration. This asserts the
    matcher fires on a constructed offender, so a future refactor cannot leave
    the scan intact while silently breaking the comparison.
    """
    sample = "the tool installs at /Users/someone/.local/bin/a2web"
    assert any(term in sample for term in _DENIED)
