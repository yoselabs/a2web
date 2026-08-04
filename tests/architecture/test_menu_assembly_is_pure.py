"""Architectural invariant: the extractor menu collects sources value-blind.

Backstops the `multi-source-extraction-input` change (ADR-0005). The class was
*value-blind single-source selection gated by a length proxy*: the extraction
ladder kept one source iff its render was longer, so a short-but-correct
structured payload silently lost (and a longer wrong one clobbered the answer).

These are *behavioral* fitness functions (implementation-agnostic):

  1. `_run_extraction_escalation` MUST collect a structured candidate even when
     its render is SHORTER than the prose baseline — if a length gate is
     re-introduced into the escalators, the short candidate vanishes and this
     fails, regardless of how the gate is coded.
  2. `assemble_menu` MUST be a pure function of its input (same candidates →
     identical bytes) — the cache-prefix byte-stability invariant (the menu IS
     the prompt-cache prefix) depends on it.

Acceptance check (re-run after any refactor):

    1. In `_escalate_via_json` / `_escalate_via_records`, re-add a
       `len(rendered) > len(prose)` gate before collecting.
    2. Run `make arch`.
    3. Confirm `test_short_structured_candidate_is_collected` fails.
    4. Revert.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from a2web.fetcher import ContentCandidate, _run_extraction_escalation, assemble_menu
from a2web.fetcher.context import FetchInputs
from a2web.models import NextLink


@dataclass
class _FakeFc:
    content_md: str = ""
    final_url: str = ""
    #: §7.2 lifted the frozen preamble off `FetchContext`; the double carries the
    #: REAL `FetchInputs` rather than a shim, so it cannot drift from the shape
    #: the code under test actually reads.
    inputs: FetchInputs = field(
        default_factory=lambda: FetchInputs(
            started_at=datetime.now(UTC), start_perf=time.perf_counter(), profile_hash="x", bypass_cache=True
        )
    )
    next_links_handler: list[NextLink] = field(default_factory=list)
    content_candidates: list[ContentCandidate] = field(default_factory=list)
    # Mirrors `FetchContext`: the escalation installs a JSON-LD-derived record
    # set here when the DOM miner found none (ADR-0015 listing index).
    record_set: object | None = None
    record_count: int | None = None
    # Mirrors `FetchContext`: the ladder installs the page's own declared
    # subject entity here (ADR-0018 / declared_entity_v4).
    declared_entity: object | None = None


# A short renderable Product payload alongside a long prose baseline. The
# payload's render is far shorter than the prose — a length gate would drop it.
_SHORT_JSON_LONG_PROSE = (
    "<html><body>"
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"ItemList","itemListElement":['
    '{"@type":"ListItem","item":{"@type":"Product","name":"P",'
    '"offers":{"price":"7","priceCurrency":"USD","url":"https://x.example/p"}}}]}'
    "</script></body></html>"
)


async def test_short_structured_candidate_is_collected() -> None:
    long_prose = "Lorem ipsum dolor sit amet. " * 200  # far longer than the JSON render
    fc = _FakeFc(content_md=long_prose, final_url="https://x.example/c")
    await _run_extraction_escalation(fc, raw_html=_SHORT_JSON_LONG_PROSE)
    json_cands = [c for c in fc.content_candidates if c.source == "json_synth"]
    assert json_cands, "a short structured candidate was dropped — length gate re-introduced?"
    assert any("7" in c.content_md for c in json_cands)


def test_assemble_menu_is_byte_stable() -> None:
    cands = [
        ContentCandidate(source="trafilatura", content_md="alpha body"),
        ContentCandidate(source="json_synth", content_md="beta rows"),
        ContentCandidate(source="record_synth", content_md="gamma records"),
    ]
    assert assemble_menu(cands) == assemble_menu(cands)
