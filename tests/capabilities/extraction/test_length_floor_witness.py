"""`LENGTH_FLOOR` bracketed by two CAPTURED pages, not by a sized fixture.

`close-guards-that-read-green` §5.3. `LENGTH_FLOOR = 500` is the single most
load-bearing number in the product — it decides whether a retrieved body counts
as content or as a thin/failed fetch, and therefore whether a2web escalates,
warns, or answers. It was measured as doublable with zero test failures.

The reason is worth stating, because it is a shape that recurs: its one
"witness" was `test_wire_content_md.py`'s `assert len(_PROSE) >= LENGTH_FLOOR`
over a fixture built as `"...36 chars..." * 20`. A fixture sized FROM the
constant cannot falsify the constant. It moves when the constant moves, so it
agrees with any value — and worse, it reads as a deliberate check.

This file brackets the constant with two pages captured off the live web, whose
extracted lengths are facts about those pages:

    example.com          113 chars  ─┐
                                     │  LENGTH_FLOOR = 500 sits here
    iana.org/help/...    740 chars  ─┘

Neither number is derived from anything in the tree. Raising the floor past 740
flips IANA from content to thin; lowering it past 113 flips example.com from
thin to content. Both directions are witnessed, which the sized fixture never
managed in either.

Captured 2026-08-02. Both pages are chosen for durability rather than
convenience: `example.com` is IANA-reserved by RFC 2606 and exists precisely to
be stable, and `/help/example-domains` is its explanatory page. Neither is a
commercial page that will be redesigned next quarter.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import trafilatura

from a2web.packages.block_detector import LENGTH_FLOOR, BlockVerdict, evaluate

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "captured"

#: (fixture, whether its extracted prose clears the floor). The lengths are
#: asserted below rather than written here — a table carrying the numbers would
#: be one more artifact to update in lockstep with the constant, which is the
#: defect this file exists to fix.
_CASES = [
    ("iana_example_domains_short_prose.html", True),
    ("example_com_tiny_page.html", False),
]


def _extracted(name: str) -> str:
    html = (_FIXTURES / name).read_text(encoding="utf-8", errors="replace")
    return trafilatura.extract(html, output_format="markdown") or ""


@pytest.mark.parametrize(("name", "clears_floor"), _CASES)
def test_a_captured_page_lands_on_the_expected_side_of_the_floor(name: str, clears_floor: bool) -> None:
    """The behavioural claim: this real page is (or is not) content.

    Fails if `LENGTH_FLOOR` moves past either page's actual extracted length —
    which is the whole point, and is what the sized fixture could never do.
    """
    prose = _extracted(name)
    assert prose, f"{name}: extraction returned nothing — the capture is stale, re-capture it"
    verdict = evaluate(content_md=prose, raw_html=(_FIXTURES / name).read_text(errors="replace"), content_type="text/html")
    if clears_floor:
        assert verdict.verdict is not BlockVerdict.length_floor, (
            f"{name} extracts {len(prose)} chars of real prose and must count as content; "
            f"LENGTH_FLOOR is {LENGTH_FLOOR}"
        )
    else:
        assert verdict.verdict is BlockVerdict.length_floor, (
            f"{name} extracts only {len(prose)} chars and must NOT be treated as a full page; "
            f"LENGTH_FLOOR is {LENGTH_FLOOR}"
        )


def test_the_two_captures_actually_bracket_the_constant() -> None:
    """Non-vacuity for the bracket itself.

    Two fixtures on the SAME side of the floor would pass every test above
    while witnessing the constant in only one direction — the sized fixture's
    failure with extra steps. This asserts the bracket is real, and it is the
    test that fails first if a re-capture drifts one page across the line.
    """
    below = len(_extracted("example_com_tiny_page.html"))
    above = len(_extracted("iana_example_domains_short_prose.html"))
    assert below < LENGTH_FLOOR < above, (
        f"the captures no longer bracket LENGTH_FLOOR={LENGTH_FLOOR}: "
        f"example.com={below}, iana={above}. Either the constant moved (state why) "
        "or a page changed (re-capture, and pick a new one if it no longer brackets)."
    )
