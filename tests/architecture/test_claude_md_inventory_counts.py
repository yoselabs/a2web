"""CLAUDE.md's inventory counts match the tree they describe.

CLAUDE.md is the map every agent reads first, and it states sizes: how many
handlers there are, how many tier manifests. Those numbers rot the moment
someone adds a file, and nothing noticed for a long time — on 2026-08-02 the
handlers were documented as five (there are nine, and four of the nine were not
even named) and the tier manifests as five (there are eight, and the missing
three included `browser_robust`, a whole escalation rung).

**A wrong count is worse than no count.** An agent reading "5 tiers" and finding
five plausible names has no reason to look further, so the omitted rung is
invisible precisely to the reader who trusted the document. That is the same
failure the citation guard exists for — a dead reference and a stale census are
both the map lying with authority.

The guard is deliberately narrow. It checks the two counts CLAUDE.md states as a
NUMBER, because a number is falsifiable and prose is not. It does not try to
verify the accompanying descriptions; that is what review is for.

Pairs with `test_claude_md_citations_resolve.py`, which checks that the paths
CLAUDE.md cites exist. This checks that the quantities it claims are true.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).parents[2]
_CLAUDE_MD = _ROOT / "CLAUDE.md"


def _module_names(directory: pathlib.Path) -> set[str]:
    """Public modules in `directory` — no dunders, no `_private` helpers."""
    return {p.stem for p in directory.glob("*.py") if not p.stem.startswith("_")}


def _manifest_listing() -> str:
    """The parenthesised tier-manifest list, isolated from the rest of the doc."""
    text = _CLAUDE_MD.read_text(encoding="utf-8")
    match = re.search(r"`tiers/` \(\d+ tiers[^)]*\)", text)
    assert match is not None, "CLAUDE.md no longer carries a `tiers/ (N tiers — …)` manifest list"
    return match.group(0)


def _claim(pattern: str) -> int:
    """The single integer CLAUDE.md states for `pattern`."""
    found = re.findall(pattern, _CLAUDE_MD.read_text(encoding="utf-8"))
    assert len(found) == 1, f"expected exactly one {pattern!r} claim in CLAUDE.md, found {len(found)}: {found}"
    return int(found[0])


def test_handler_count_word_matches() -> None:
    """The count is written as a WORD (`**Nine:**`), so check it as one."""
    handlers = _module_names(_ROOT / "src" / "a2web" / "handlers")

    # Non-vacuity: a walk that found nothing would pass any equality it wrote.
    assert len(handlers) >= 5, f"handler discovery returned {handlers} — the walk is broken, not the doc"

    words = {5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve"}
    expected = words.get(len(handlers))
    assert expected is not None, f"{len(handlers)} handlers — extend the word table"

    text = _CLAUDE_MD.read_text(encoding="utf-8")
    assert f"**{expected}:** `arxiv.py`" in text, (
        f"CLAUDE.md's handler count is stale: {len(handlers)} handlers on disk "
        f"({sorted(handlers)}), so the line should read `**{expected}:**`"
    )


def test_every_handler_is_named_not_just_counted() -> None:
    """A count with an incomplete list is the worse half of the defect.

    CLAUDE.md said five and named five — of nine. A reader who counts the names
    and finds them consistent has no signal at all that four are missing.
    """
    handlers = _module_names(_ROOT / "src" / "a2web" / "handlers")
    text = _CLAUDE_MD.read_text(encoding="utf-8")

    missing = sorted(h for h in handlers if f"`{h}.py`" not in text)
    assert not missing, f"handlers on disk but never named in CLAUDE.md: {missing}"


def test_tier_manifest_count_is_real() -> None:
    manifests = _module_names(_ROOT / "src" / "a2web" / "_manifests" / "tiers")

    assert len(manifests) >= 5, f"manifest discovery returned {manifests} — the walk is broken, not the doc"

    claimed = _claim(r"`tiers/` \((\d+) tiers")
    assert claimed == len(manifests), f"CLAUDE.md claims {claimed} tier manifests; {len(manifests)} exist ({sorted(manifests)})"


def test_every_tier_manifest_is_named() -> None:
    """Scoped to the manifest LIST, not the whole document — deliberately.

    The first version of this test searched all of CLAUDE.md and passed when
    `browser_robust` was deleted from the list, because the name also appears in
    the tiers paragraph and in `browser_robust_backend`. A guard that any
    incidental mention satisfies is not checking the list at all — caught by
    mutation, which is the only reason it is not still shipping green.
    """
    manifests = _module_names(_ROOT / "src" / "a2web" / "_manifests" / "tiers")
    listing = _manifest_listing()

    missing = sorted(m for m in manifests if f"`{m}`" not in listing)
    assert not missing, f"tier manifests on disk but absent from CLAUDE.md's manifest list: {missing}"
