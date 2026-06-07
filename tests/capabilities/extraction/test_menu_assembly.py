"""Multi-source extractor menu (ADR-0005, change `multi-source-extraction-input`).

The extractor is fed the *menu* — every rung that produced output — not a
single length-gated winner. These tests prove, deterministically and with no
LLM, that:

  - a short structured payload's answer reaches the menu even when a junk
    record region is far longer (the retired volume gate would have dropped it);
  - the JSON rung emits ALL renderable payloads, not just the top-ranked one;
  - `assemble_menu` is a pure, dedup-ing, order-stable function of its input.

The wire `content_md` default is unchanged (legacy selection) — asserted in
`test_extraction_ladder.py`; this file is about the extractor *input*.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from a2web.fetcher import ContentCandidate, _run_extraction_escalation, assemble_menu
from a2web.models import NextLink


@dataclass
class _FakeFc:
    content_md: str = ""
    final_url: str = ""
    start_perf: float = field(default_factory=time.perf_counter)
    next_links_handler: list[NextLink] = field(default_factory=list)
    content_candidates: list[ContentCandidate] = field(default_factory=list)


# A short JSON-LD ItemList whose single Product carries the answer token (a
# distinctive price), plus a LONG junk record region. Under the retired volume
# gate the records (far longer) won and the JSON was dropped — so the answer
# never reached the extractor. The menu must now carry both.
_ANSWER_TOKEN = "4242"
_PAGE_HTML = (
    "<html><body>"
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"ItemList","itemListElement":['
    '{"@type":"ListItem","item":{"@type":"Product","name":"Widget XYZ",'
    '"offers":{"@type":"Offer","price":"' + _ANSWER_TOKEN + '","priceCurrency":"USD",'
    '"url":"https://shop.example.com/widget-xyz"}}}]}'
    "</script>"
    "<div class='listing'>"
    + "".join(
        "<article class='row'>"
        f"<h3><a href='/item/{i}'>Unrelated catalogue row number {i} headline text</a></h3>"
        f"<p>A long filler description for row {i} that pads the record render well "
        "past the short JSON payload so the old length proxy would have dropped it.</p>"
        "</article>"
        for i in range(12)
    )
    + "</div></body></html>"
)


async def test_short_json_answer_reaches_menu_despite_longer_records() -> None:
    fc = _FakeFc(content_md="some thin trafilatura prose", final_url="https://shop.example.com/c")
    await _run_extraction_escalation(fc, raw_html=_PAGE_HTML)

    menu = assemble_menu(fc.content_candidates)
    # The answer-bearing JSON payload survives (the menu fix) ...
    assert _ANSWER_TOKEN in menu, "short JSON answer was dropped from the extractor menu"
    # ... alongside the longer record render — both sources present, not either/or.
    assert "catalogue row number" in menu
    # And the prose baseline is in the menu too.
    assert "trafilatura prose" in menu
    sources = {c.source for c in fc.content_candidates}
    assert {"trafilatura", "json_synth", "record_synth"} <= sources


async def test_json_rung_emits_all_renderable_payloads() -> None:
    # Two distinct renderable ItemLists: the answer is in the SECOND (lower
    # ranked) one. The old rung rendered the first then `break`ed — losing it.
    html = (
        "<html><body>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"ItemList","itemListElement":['
        '{"@type":"ListItem","item":{"@type":"Product","name":"First list item",'
        '"offers":{"price":"11","priceCurrency":"USD","url":"https://x.example/1"}}}]}'
        "</script>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"ItemList","itemListElement":['
        '{"@type":"ListItem","item":{"@type":"Product","name":"Second list item",'
        '"offers":{"price":"99","priceCurrency":"USD","url":"https://x.example/2"}}}]}'
        "</script>"
        "</body></html>"
    )
    fc = _FakeFc(content_md="prose", final_url="https://x.example/c")
    await _run_extraction_escalation(fc, raw_html=html)
    json_renders = "\n".join(c.content_md for c in fc.content_candidates if c.source == "json_synth")
    assert "11" in json_renders and "99" in json_renders, "JSON rung dropped a non-top-ranked payload"


def test_assemble_menu_is_pure_and_dedups() -> None:
    cands = [
        ContentCandidate(source="trafilatura", content_md="the full prose body with detail"),
        ContentCandidate(source="json_synth", content_md="prose body"),  # strict subset -> dropped
        ContentCandidate(source="record_synth", content_md="records render block"),
        ContentCandidate(source="json_synth", content_md="records render block"),  # exact dup -> dropped
    ]
    out1 = assemble_menu(cands)
    out2 = assemble_menu(cands)
    assert out1 == out2, "assemble_menu is not a pure function of its input"
    assert "the full prose body with detail" in out1
    assert "records render block" in out1
    assert out1.count("records render block") == 1, "exact-duplicate candidate not suppressed"
    # The strict-subset 'prose body' candidate is suppressed (it is a substring
    # of the prose), so only the labelled prose + records blocks remain.
    assert out1.count("## source:") == 2
