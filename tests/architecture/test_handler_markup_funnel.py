"""Architectural invariant: handlers parse markup with a DOM, never a regex.

On 2026-07-28 two handler parsers were found silently dead — returning zero rows
against live pages holding 47 entries and 1066 links. Both were regexes over
markup, and both broke on changes that carry no meaning: arXiv started serving
`<a href ="…">` with single-quoted attributes, Parsoid switched from
`href="/wiki/X"` to a relative `href="./X"`. Neither site changed what its page
SAID; both changed how it was spelled, and a regex cannot tell those apart.

The failure mode is what makes this worth a guard rather than a fix: a rotted
regex does not raise, it returns `[]`, and every caller reads `[]` as "the page
is empty". Both parsers had green suites. The live handler probe passed both.
Nothing anywhere reported it.

**The rule is structural on purpose, and the obvious rule does not work.** The
first attempt classified each pattern by looking for markup in its text, and it
failed in BOTH directions: `(?P<name>` named groups read as markup (`<n`), while
`listing_oracle`'s `rel\\s*=\\s*["']?…` was MISSED — searching for `rel\\s*=`
does not match that text, because the target is itself a regex where `\\s*` is
a literal backslash-s-star, not whitespace. Regexing a regex to decide whether
it concerns markup is exactly as brittle as the thing it polices.

So the rule keys on shape instead: **in `handlers/`, every `re.compile` pattern
must be an anchored URL path.** When this was written all 18 legitimate patterns
were anchored path matchers (`^/r/…`, `^/abs/…`) and all 4 rotted ones were not
— the split is clean, and it does not require deciding what HTML looks like.

Markup goes through `dom_schema.extract`, which additionally reports WHY a parse
yielded nothing (`ROT` = the schema stopped matching, vs `EMPTY` = the page
really is empty) — the distinction whose absence let this rot for so long.

Acceptance check (re-run after any refactor):

    1. Open `src/a2web/handlers/arxiv.py`.
    2. Add `_X = re.compile(r'<div class="thing">')` at module scope.
    3. Run `make arch`.
    4. Confirm this test fails naming that file and line.
    5. Revert.
"""

from __future__ import annotations

import ast

from ._walk import SRC_ROOT, walked_files

#: Handler modules are ~12 files; the floor exists so a moved source root fails
#: loudly instead of finding nothing to object to and reporting green.
_MIN_FILES = 8

#: A pattern this guard permits: an anchored path matcher. Handlers legitimately
#: regex the URL path to decide `matches(url)` and to pull ids out of it — that
#: is text, not markup, and regex is the right tool.
_ALLOWED_PREFIXES = ("^/", "^(/", "^([", "^\\d", "^[")

#: Patterns exempt from the anchored-path rule, and WHY. A table rather than a
#: scattering of inline suppressions, so an exemption is a visible reviewed edit whose
#: reason the next auditor can re-read.
#:
#: `_reddit_html._COUNT_RE` runs over `span.text()` / `link.text()` — the text of
#: a node the DOM parser already produced. That is the RIGHT side of this guard's
#: line: the markup was parsed, and pulling "1,234" out of the resulting string
#: is exactly what a regex is for. It fails the anchored-path shape only because
#: it is not about a URL.
#:
#: Add here only for a pattern that runs on ALREADY-PARSED text. A pattern that
#: touches raw markup does not belong in this table under any justification.
_EXEMPT: frozenset[tuple[str, str]] = frozenset(
    {
        ("_reddit_html.py", r"(\d[\d,]*)"),
    }
)


def _is_anchored_path(pattern: str) -> bool:
    return pattern.startswith(_ALLOWED_PREFIXES)


def _handler_files() -> list:
    return [p for p in walked_files(SRC_ROOT, minimum=_MIN_FILES) if p.parent.name == "handlers"]


def _violations() -> list[str]:
    offenders: list[str] = []
    files = _handler_files()
    assert len(files) >= _MIN_FILES, f"only {len(files)} handler modules walked — the source root moved"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "compile"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "re"
            ):
                continue
            try:
                pattern = ast.literal_eval(node.args[0])
            except (ValueError, IndexError):  # dynamic pattern — cannot classify, do not guess
                continue
            if not isinstance(pattern, str) or _is_anchored_path(pattern):
                continue
            if (path.name, pattern) in _EXEMPT:
                continue
            offenders.append(f"  {path.name}:{node.lineno} — {pattern[:60]}")
    return sorted(offenders)


def test_the_walk_is_not_vacuous() -> None:
    """A guard that inspected nothing cannot object to anything."""
    assert len(_handler_files()) >= _MIN_FILES


def test_every_exemption_is_real() -> None:
    """An exemption that no longer describes a live pattern is rot in the guard.

    Without this the table silently accumulates entries for code that moved or
    was deleted, and a future reader cannot tell a reviewed exception from a
    fossil.
    """
    live = {
        (path.name, ast.literal_eval(node.args[0]))
        for path in _handler_files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "compile"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "re"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    stale = _EXEMPT - live
    assert not stale, f"exemptions no longer matching any pattern: {sorted(stale)}. Delete them."


def test_handlers_do_not_regex_markup() -> None:
    offenders = _violations()
    assert not offenders, (
        "handler regexes that are not anchored URL paths:\n"
        + "\n".join(offenders)
        + "\n\nParse markup with `dom_schema.extract(html, Schema(...))`, not a regex. A regex over "
        "markup breaks on quote style, attribute order and whitespace — none of which change what a "
        "page means — and it breaks SILENTLY, returning [] that every caller reads as 'the page is "
        "empty'. That is how the arXiv listing (47 entries) and wikipedia wikilink (1066 anchors) "
        "parsers both returned 0 for months behind green tests. If this pattern really is about a "
        "URL path, anchor it (`^/…`)."
    )
