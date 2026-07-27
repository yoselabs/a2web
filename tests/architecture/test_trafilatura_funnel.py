"""Architectural invariant: HTML extraction is funneled through `content_extract`.

The shelf's `content_extract.extract_markdown(html, url, *, include_links=False)`
returns markdown AND links AND headings AND metadata from ONE off-thread parse.
A bare `trafilatura.extract(...)` returns markdown only. So every direct call
silently discards the links and headings its caller never knew were available —
and that is not hypothetical, it is how `other_pages` became impossible to emit
on every pre-rendering tier (`eval/findings_2026-07-28.md`).

**This guard exists because promotion did not help.** The chronology:

    2026-05-10  tiers/browser.py added WITH its own trafilatura.extract,
                while fetcher.py imported the canonical extract_markdown
                the SAME DAY
    2026-05-12  that extractor promoted to packages/content_extract
    2026-07-08  promoted again to the shelf, in-tree copy deleted

Each promotion moved the correct copy further up the stack and left the bypass
untouched. The distance grew and nothing noticed, because "is everyone using the
canonical thing?" was never a checked property. Moving more code to the shelf
would have made this worse, not better.

Mirrors `test_json_loads_funnel.py`, which is the only other funnel this repo
enforces and which has exactly the same shape. Note what is banned: the *call*,
not the import — a module may legitimately reference trafilatura for a type or
an exception without going around the funnel.

Acceptance check (re-run after any refactor):

    1. Open `src/a2web/tiers/browser.py`.
    2. Add `_ = trafilatura.extract("<p>x</p>")` anywhere.
    3. Run `make arch`.
    4. Confirm this test fails with a precise file:line.
    5. Revert.
"""

from __future__ import annotations

import ast

from ._walk import SRC_ROOT, walked_files

#: Modules allowed to reach the library directly, and WHY. A table rather than a
#: scattering of `# noqa`, so an exemption is a visible reviewed edit and the
#: reason is re-readable by the next person who audits this.
#:
#: Both entries exist for ONE reason: the shelf's
#: `content_extract.extract_markdown(html, url, *, include_links=False)` exposes
#: no `include_comments` knob, and these two handlers pass
#: `include_comments=True` because on a comment thread the comments ARE the
#: content. Routing them through the shelf today would silently drop the page's
#: substance — a worse regression than the missing links this funnel exists to
#: prevent.
#:
#: This is a SHELF GAP, not a permanent a2web exception. The fix is to promote
#: the knob into `content_extract` and then delete these entries. Tracked in
#: BACKLOG.md. Do not add to this table for any other reason.
_FUNNEL_EXEMPT: frozenset[str] = frozenset(
    {
        "handlers.reddit",
        "handlers.twitter",
    }
)

#: Population floor. `src/a2web/` is ~70 modules; the floor exists so a moved
#: source root fails loudly instead of finding nothing to object to and
#: reporting green. Do NOT lower it to make a refactor pass.
_MIN_FILES = 40

_CANONICAL = (
    "content_extract.extract_markdown(html, url, include_links=True) — returns "
    "markdown, links, headings and metadata from one off-thread parse. For "
    "metadata alone use content_extract.parse_metadata()."
)


def _trafilatura_aliases(tree: ast.AST) -> set[str]:
    """Every name in this module that resolves to the trafilatura module."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "trafilatura" or alias.name.startswith("trafilatura."):
                    aliases.add(alias.asname or alias.name.split(".")[0])
    return aliases


def _direct_calls(tree: ast.AST, aliases: set[str]) -> list[tuple[int, str]]:
    """`<alias>.<anything>(...)` call sites — the funnel bypass."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in aliases:
            found.append((node.lineno, f"{func.value.id}.{func.attr}"))
    return found


def _from_imports(tree: ast.AST) -> list[tuple[int, str]]:
    """`from trafilatura import extract` — a bypass that leaves no attribute call."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "trafilatura":
            names = ", ".join(a.name for a in node.names)
            found.append((node.lineno, f"from {node.module} import {names}"))
    return found


def _violations() -> list[str]:
    offenders: list[str] = []
    files = walked_files(SRC_ROOT, minimum=_MIN_FILES)
    for path in files:
        rel = path.relative_to(SRC_ROOT.parent.parent)
        if str(path.relative_to(SRC_ROOT)).replace("/", ".").removesuffix(".py") in _FUNNEL_EXEMPT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _trafilatura_aliases(tree)
        for lineno, what in _direct_calls(tree, aliases) + _from_imports(tree):
            offenders.append(f"  {rel}:{lineno} — {what}")
    return sorted(offenders)


def test_the_walk_is_not_vacuous() -> None:
    """A guard that inspected nothing cannot object to anything."""
    walked_files(SRC_ROOT, minimum=_MIN_FILES)


def test_html_extraction_funnels_through_content_extract() -> None:
    offenders = _violations()
    assert not offenders, (
        "direct trafilatura calls bypassing the canonical extractor:\n"
        + "\n".join(offenders)
        + "\n\nUse "
        + _CANONICAL
        + "\nA bare trafilatura.extract returns markdown ONLY — it silently drops the "
        "links and headings the canonical extractor returns from the same parse. That "
        "is how the link index was lost on every pre-rendering tier; see "
        "eval/findings_2026-07-28.md."
    )
