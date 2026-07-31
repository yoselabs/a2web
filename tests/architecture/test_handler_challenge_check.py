"""A handler that extracts prose from retrieved HTML must check for a wall.

`twitter.py` and `wikipedia.py` both did. `reddit.py::_fetch_old_reddit` — the
same shape, GET HTML then trafilatura then return — did not, so ANY page that
extracted to prose came back `Verdict.ok`, including a "whoa there, pardner"
block and an over-18 gate. A challenge page extracts perfectly well; that is
precisely why the check has to exist.

Fixing the one site fixes today's instance. This makes it a property: the next
handler to grow an HTML fallback either calls `challenge_verdict` or turns this
red. The rule is deliberately structural rather than a review convention —
the defect it catches is invisible in a green suite, because every test of a
*good* page passes with or without the check.

Per the anti-vacuity rule this asserts it found candidates. A walk matching
zero extractor calls reads identical to a passing one, and that failure mode
has already cost this repo twice.
"""

from __future__ import annotations

import ast

from tests.architecture._walk import SRC_ROOT, walked_files

HANDLERS_ROOT = SRC_ROOT / "handlers"

#: Generic prose extractors — the ones that turn ARBITRARY HTML into text with
#: no idea whether that HTML is a page or an interstitial. Exactly two spellings
#: reach that: bare `trafilatura.extract` (reddit, twitter — the two handlers
#: the trafilatura-funnel guard exempts) and the shelf's `extract_markdown`
#: (wikipedia).
#:
#: The set is deliberately NARROW, and the first draft was wrong for being wide.
#: It matched bare `extract` and `to_markdown`, which flagged six more handlers —
#: every one a false positive. `dom_schema.extract(html, _LISTING_SCHEMA)` reads
#: NAMED SELECTORS and yields nothing on a challenge page; `to_markdown` in
#: hn.py runs on an API field, not on retrieved markup. Neither can launder an
#: interstitial into content, which is the only thing this guard is about.
#: Hence the qualified match below: `trafilatura.extract` counts, a bare
#: `extract` does not.
_QUALIFIED_EXTRACTORS = frozenset({("trafilatura", "extract")})
_BARE_EXTRACTORS = frozenset({"extract_markdown"})

#: Modules whose extractor call is provably not on a retrieval path. Each entry
#: needs a reason, and the population assertion below keeps the list from
#: quietly swallowing the whole tree.
_EXEMPT: dict[str, str] = {}


class _ModuleScan(ast.NodeVisitor):
    """Record whether a module calls a generic extractor and/or the wall check."""

    def __init__(self) -> None:
        self.extractor_calls: list[str] = []
        self.checks_challenge = False

    def visit_Call(self, node: ast.Call) -> None:
        name = _extractor_name(node.func)
        if isinstance(node.func, ast.Name) and node.func.id == "challenge_verdict":
            self.checks_challenge = True
        elif name is not None:
            self.extractor_calls.append(name)
        self.generic_visit(node)


def _extractor_name(func: ast.expr) -> str | None:
    """Name of the generic extractor being called, or `None` for anything else."""
    if isinstance(func, ast.Name) and func.id in _BARE_EXTRACTORS:
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and (func.value.id, func.attr) in _QUALIFIED_EXTRACTORS:
        return f"{func.value.id}.{func.attr}"
    return None


def test_every_html_extracting_handler_checks_for_a_challenge() -> None:
    extracting: dict[str, list[str]] = {}
    offenders: list[str] = []

    for path in walked_files(HANDLERS_ROOT, minimum=8):
        if path.name == "_common.py":
            continue  # defines `challenge_verdict`; does not extract
        scan = _ModuleScan()
        scan.visit(ast.parse(path.read_text(encoding="utf-8")))
        if not scan.extractor_calls:
            continue
        extracting[path.name] = scan.extractor_calls
        if path.name in _EXEMPT or scan.checks_challenge:
            continue
        offenders.append(
            f"{path.name} calls {sorted(set(scan.extractor_calls))} on retrieved HTML "
            "but never calls challenge_verdict — a challenge page extracts to prose "
            "and will be reported as content (ADR-0009)"
        )

    # NON-VACUITY. Without this the guard passes when the walk matches nothing:
    # a renamed extractor, a moved handlers root, or a typo in the name set all
    # produce "0 offenders in 0 candidates", which is indistinguishable from a
    # clean tree. Three is the exact known population (reddit, twitter,
    # wikipedia) — a floor rather than a count, but there is nothing below it
    # to leave room for: fewer than three means the matcher stopped working.
    assert len(extracting) >= 3, (
        f"expected at least 3 handlers extracting prose from HTML, found {len(extracting)}: "
        f"{sorted(extracting)}. The known population is reddit, twitter and wikipedia; "
        "the guard is not seeing the code it exists to check. Most likely the extractor "
        "moved behind a new name (update the extractor sets) rather than the handlers "
        "genuinely stopping."
    )

    assert not offenders, "\n".join(offenders)


def test_the_exemption_list_names_only_real_modules() -> None:
    """An exemption for a module that no longer exists is a stale excuse.

    Empty today, and this keeps it honest if it ever is not: an entry that
    stops matching a real file would otherwise sit there suppressing nothing
    while reading as a considered decision.
    """
    present = {p.name for p in walked_files(HANDLERS_ROOT, minimum=8)}
    stale = sorted(set(_EXEMPT) - present)
    assert not stale, f"_EXEMPT names modules that no longer exist: {stale}"
