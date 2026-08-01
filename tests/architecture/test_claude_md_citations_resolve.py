"""Every path `CLAUDE.md` cites as current actually exists.

`CLAUDE.md` is the first file every agent reads and the map they navigate the
codebase by. On 2026-07-27 it cited five things that do not exist:

  * `src/a2web/_plugin.py` — promoted to the shelf as `plugin_surface`
  * `tests/test_packages_independence.py` — deleted; `tach.toml` took over
  * `tools/hooks/install.py` — lives in the shelf, never in this repo
  * `packages/llm_cost_guard.py` — promoted to the shelf as `anyllm.cost`
  * `ndjson_log` — a retired package still listed as current

The second one is why this guard is not cosmetic. `CLAUDE.md` named a deleted
test file as the enforcer of the packages-boundary invariant, so an agent
checking whether that invariant was covered got a confident answer pointing at
nothing — while the real mechanism (`tach.toml`) had a coverage hole that let
an unlisted package import domain code freely. The inaccurate map is how the
unenforced invariant survived. A stale citation is not untidiness; it is a
wrong answer delivered with authority to a reader who cannot cheaply check it.

**Historical mentions stay writable.** "the cache seam … was
`packages/http_cache.py`" is a record of a promotion, and the path is the
informative part — rewriting it into prose that omits the path would delete the
information to satisfy a lint. So a mention may opt out with a marker
immediately after it:

    was `packages/http_cache.py`<!-- gone -->

Chosen over an allowlist inside this test because the justification belongs
beside the sentence it justifies, not in a different file that rots the same
way. Chosen in HTML-comment form because `CLAUDE.md` is read both rendered and
raw, and this disappears in the first without lying in the second. Same
reasoning as the `# SPIKE-ARCHIVED:` convention: an explicit, reviewable
sentence beats silent rot, and the escape hatch has to cost one edit at the
point of writing or it will be routed around.

**Deliberately not enforced:** that a marked path is genuinely gone. A marker on
a live path is harmless (it only forgoes a check), and enforcing it would make
the guard fail on the ordinary case of a file being re-created at an old path.
The asymmetry is intentional — the damage is an unmarked dead citation, not a
marked live one.
"""

from __future__ import annotations

import pathlib
import re

from ._walk import REPO_ROOT, SRC_ROOT

_CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

#: A backticked PATH citation: at least one slash, ending in a source-ish
#: suffix. The trailing group captures whatever immediately follows the closing
#: backtick, so the opt-out marker can be detected without a second pass.
#:
#: Bare filenames (`raw.py`, `jina.py`) are deliberately out of scope. They are
#: written inside a sentence that establishes their directory — "`src/a2web/tiers/`
#: … `raw.py` (curl_cffi), `jina.py`" — so resolving one means guessing which
#: directory the prose meant, and a guess that lands on a same-named file
#: elsewhere in the tree would report green for the wrong reason. A guard that
#: can be confidently wrong is worse than one with a stated blind spot.
_CITATION = re.compile(r"`([a-zA-Z0-9_\-.]+(?:/[a-zA-Z0-9_\-.]+)+\.(?:py|md|toml|yaml|yml|json))`(.{0,14})")

#: `path/to/file.py::function` — the form the dead
#: `tests/packages/test_zendriver_backend.py::test_fake_config_matches_real_add_argument`
#: citation used. The plain `_CITATION` pattern above required the backtick to
#: close right after the extension, so a `::function` suffix meant the whole
#: citation matched NOTHING and was never checked at all.
_CITATION_WITH_FUNC = re.compile(r"`([a-zA-Z0-9_\-.]+(?:/[a-zA-Z0-9_\-.]+)+\.py)::([a-zA-Z0-9_]+)`(.{0,14})")

#: A trailing-slash directory citation (`openspec/changes/sunset-a2kit-dependency/`).
#: Also invisible to `_CITATION`, which demands a file extension — which is how
#: two CLAUDE.md citations kept pointing at changes that had moved under
#: `archive/`.
_CITATION_DIR = re.compile(r"`([a-zA-Z0-9_\-.]+(?:/[a-zA-Z0-9_\-.]+)*/)`(.{0,14})")

#: The opt-out. Must sit immediately after the citation it applies to.
_GONE_MARKER = "<!-- gone -->"

#: Roots a citation may be written relative to. `CLAUDE.md` uses repo-relative
#: paths (`tests/architecture/_walk.py`) and `src/a2web`-relative shorthand
#: (`wobble/_policies.py`, `actions/playbook.py`) interchangeably. Demanding one
#: form would rewrite the file's voice to suit a test.
_ROOTS = (
    REPO_ROOT,
    SRC_ROOT,
    REPO_ROOT / "src",
    SRC_ROOT / "packages",
    SRC_ROOT / "packages" / "llm_extract",
    SRC_ROOT / "_manifests",
)

#: Floor on extracted citations. Population is 43 path-shaped citations, of
#: which 1 is marked historical. This fails loudly if the file's markup changes
#: out from under the pattern, rather than silently checking nothing and
#: reporting green.
_MIN_CITATIONS = 25


#: Every document agents navigate by. `verification-provenance.md` is here
#: because it cited a nonexistent test TWICE while codifying the rule that
#: load-bearing claims need a foreign witness — the document was an endogenous
#: oracle about its own coverage, and nothing in the loop could disagree.
#:
#: `openspec/specs/` and `docs/adr/` joined on 2026-08-01. They were outside the
#: guard's window for its whole life, and the cost was measured, not guessed: 17
#: dead citations survived there — ten in `openspec/specs/` alone, including
#: eleven sites naming `tests/test_packages_independence.py` as the enforcer of
#: the packages boundary. That is the SAME dead path this guard's docstring
#: opens by describing, still being cited as live, in the documents that define
#: the capabilities, while the guard reported green.
#:
#: The lesson, recorded because it generalises: **a guard's scope is not the
#: fix's scope.** `close-silent-enforcement-loss` found a class of defect
#: (citations of things that no longer exist), built a guard, and pointed it at
#: the one file where the defect had been noticed. The class lived on
#: everywhere else. When a guard is built for a class, the repair covers the
#: class — otherwise the guard's window becomes the new definition of the
#: problem.
_DOCS = (
    _CLAUDE_MD,
    REPO_ROOT / "docs" / "architecture" / "README.md",
    REPO_ROOT / "docs" / "architecture" / "verification-provenance.md",
)


def _navigational_docs() -> list[pathlib.Path]:
    """Every doc a reader navigates the CURRENT system by.

    Deliberately excludes `docs/history/` and `docs/findings/`. Those are dated
    records: `A2KIT_FEEDBACK_v0.39.md` cites `a2kit/packages/testing/fixtures.py`
    — a path in a DIFFERENT repository that was correct when written and is not
    a2web's to fix. Demanding those resolve would either force a marker onto
    every sentence of a finished record or, worse, invite someone to edit the
    record so a test passes. A record describes the past; only a map has to be
    right about the present.
    """
    docs = [*_DOCS]
    docs += sorted((REPO_ROOT / "docs" / "adr").glob("*.md"))
    docs += sorted((REPO_ROOT / "openspec" / "specs").glob("*/spec.md"))
    return [d for d in docs if d.exists()]


def _citations_in(doc: pathlib.Path) -> list[tuple[str, bool]]:
    """Every cited path in one doc, paired with whether it opted out."""
    text = doc.read_text(encoding="utf-8")
    return [(path, trailing.startswith(_GONE_MARKER)) for path, trailing in _CITATION.findall(text)]


def _citations() -> list[tuple[str, bool]]:
    """Every cited path in CLAUDE.md, paired with whether it opted out."""
    found = _citations_in(_CLAUDE_MD)
    assert len(found) >= _MIN_CITATIONS, (
        f"extracted {len(found)} path citation(s) from CLAUDE.md, expected at least "
        f"{_MIN_CITATIONS}. The file's markup changed and this guard is no longer "
        "reading it — fix the pattern, do not lower the floor."
    )
    return found


def test_the_extraction_is_not_vacuous() -> None:
    """A guard that found no citations cannot object to any of them."""
    _citations()


def test_every_current_citation_resolves() -> None:
    missing = sorted({path for path, is_historical in _citations() if not is_historical and not _resolves(path)})
    assert not missing, _stale_message("CLAUDE.md", missing)


#: Floor for the widened walk. Measured population on 2026-08-01 was 109 across
#: `docs/architecture/`, `docs/adr/` and `openspec/specs/`. Set well below it so
#: ordinary editing does not trip the floor, but far enough above zero that a
#: glob returning nothing — a renamed directory, a changed layout — fails loudly
#: instead of reporting green over an empty set.
_MIN_NAVIGATIONAL_CITATIONS = 60


def test_the_widened_walk_is_not_vacuous() -> None:
    """The floor that makes the test below mean something.

    Without it, `openspec/specs/*/spec.md` matching nothing (a layout change, a
    move to nested capabilities) reads exactly like a clean tree.
    """
    docs = _navigational_docs()
    assert len(docs) >= 10, f"expected the navigational set to span many docs, walked {len(docs)}"

    total = sum(len(_citations_in(doc)) for doc in docs)
    assert total >= _MIN_NAVIGATIONAL_CITATIONS, (
        f"extracted {total} path citation(s) across {len(docs)} navigational doc(s), "
        f"expected at least {_MIN_NAVIGATIONAL_CITATIONS} — the pattern or the "
        "layout changed and this guard is reading far less than it thinks. Fix "
        "the walk, do not lower the floor."
    )


def test_every_navigational_doc_cites_only_live_paths() -> None:
    """The specs and ADRs, held to the same bar as CLAUDE.md.

    An `openspec/specs/` requirement naming a module that no longer exists is
    worse than the same mistake in prose: the spec is what a change is validated
    AGAINST, so the stale path is load-bearing on the next change's design.
    """
    broken: dict[str, list[str]] = {}
    for doc in _navigational_docs():
        stale = sorted({path for path, is_historical in _citations_in(doc) if not is_historical and not _resolves(path)})
        if stale:
            broken[str(doc.relative_to(REPO_ROOT))] = stale

    assert not broken, _stale_message(
        "navigational docs",
        [f"{doc}: {path}" for doc, paths in sorted(broken.items()) for path in paths],
    )


def _stale_message(where: str, missing: list[str]) -> str:
    return (
        f"{where} cite path(s) that do not exist:\n"
        + "".join(f"  {path}\n" for path in missing)
        + "\nAgents navigate by these files, so a stale citation is a wrong answer "
        "delivered with authority. Either:\n"
        "  * correct the path (a promoted module usually moved to the shelf — check "
        "what the promotion renamed it to), or\n"
        f"  * if the mention is RECORDING history, append `{_GONE_MARKER}` "
        "immediately after it.\n"
        "Do not delete the path from the sentence to pass this test — in a "
        "historical mention the path is the information."
    )


def _resolves(path: str) -> bool:
    return any((root / path).exists() for root in _ROOTS)


# --------------------------------------------------------------------- #
# `path::function` and directory citations, across every navigational doc
# --------------------------------------------------------------------- #


def _doc_text(doc: pathlib.Path) -> str:
    return doc.read_text(encoding="utf-8") if doc.exists() else ""


def test_function_citations_resolve() -> None:
    """A cited `file.py::function` must exist AND define that function.

    The file existing is not enough: `verification-provenance.md` cited
    `tests/packages/test_zendriver_backend.py::test_fake_config_matches_real_add_argument`,
    and it was the whole citation that was dead. Checking only the path would
    have let a renamed function keep reading as coverage.
    """
    checked = 0
    broken: list[str] = []
    for doc in _DOCS:
        for path, func, trailing in _CITATION_WITH_FUNC.findall(_doc_text(doc)):
            if trailing.startswith(_GONE_MARKER):
                continue
            checked += 1
            target = next((root / path for root in _ROOTS if (root / path).exists()), None)
            if target is None:
                broken.append(f"{doc.name}: {path}::{func} — file does not exist")
            elif f"def {func}" not in target.read_text(encoding="utf-8"):
                broken.append(f"{doc.name}: {path}::{func} — file exists, function does not")
    assert not broken, "citations naming a function that does not resolve:\n" + "".join(f"  {b}\n" for b in broken)
    # No floor: the population is legitimately allowed to reach zero (the only
    # two known instances were dead and were removed). Asserting a minimum here
    # would force the docs to keep a citation shape they no longer use.


def _is_intentionally_untracked(path: str) -> bool:
    """True for a path `.gitignore` says the repo does not carry.

    `eval/runs/` is cited by CLAUDE.md and is *supposed* to be absent — the same
    sentence calls it "gitignored, regenerable". Demanding it exist would force
    a generated directory to be committed to satisfy a test.

    This distinction is why the guard's first run passed locally and failed in
    CI: my working tree had `eval/runs/` from actual bench runs, and a
    `__pycache__` under a manifest surface with no tracked files. A fresh clone
    had neither. **The guard was reading my machine, not the repository** — the
    same endogenous-oracle failure it was written to catch, one level down.
    """
    ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    entries = {line.strip().rstrip("/") for line in ignore if line.strip() and not line.startswith("#")}
    return path.rstrip("/") in entries


def test_directory_citations_resolve() -> None:
    """A cited directory must exist — a change that moved under `archive/` does not."""
    checked = 0
    broken: list[str] = []
    for doc in _DOCS:
        for path, trailing in _CITATION_DIR.findall(_doc_text(doc)):
            if trailing.startswith(_GONE_MARKER) or _is_intentionally_untracked(path):
                continue
            checked += 1
            if not any((root / path).is_dir() for root in _ROOTS):
                broken.append(f"{doc.name}: {path}")
    assert checked >= 5, f"non-vacuous: expected directory citations, found {checked} — the pattern stopped matching"
    assert not broken, (
        "citations pointing at directories that do not exist:\n"
        + "".join(f"  {b}\n" for b in broken)
        + "\nAn openspec change that shipped has moved under `changes/archive/<date>-<name>/`."
    )


def test_every_navigational_doc_is_actually_read() -> None:
    """Anti-vacuity for the two tests above: a missing doc must not read green."""
    for doc in _DOCS:
        assert doc.exists(), f"{doc} does not exist — the citation guard is checking nothing for it"
        assert doc.read_text(encoding="utf-8").strip(), f"{doc} is empty"
