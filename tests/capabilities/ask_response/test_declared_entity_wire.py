"""`query` relays the page's own subject declaration, capped and declared.

`query` withholds the body by default, so the caller — itself an agent that
never sees it — is blind to everything the answer did not surface (ADR-0015).
The publisher's own JSON-LD is the cheapest faithful index available: already
parsed, **zero generation tokens**, **zero model wobble**.

Measured (`eval/spikes/declared_entity_v4.py`, 8 pages x 2 reps): on pages
declaring a subject entity, `answer + declared` beats `answer` by +0.095
coverage (95% CI [+0.010, +0.180]) and is statistically indistinguishable from
`answer + an LLM-generated entity block` — which costs ~161 completion tokens
and is 58% type-stable. Same delivery; one side is free and exact.

The cap is measured too (`declared_cap_v5.py`): coverage saturates at ~20
fields — cutting to 10 loses significant coverage, going past 20 gains nothing
measurable and doubles the wire cost.

These tests drive the real pipeline, not the model in isolation, so they fail
if the ladder stops capturing or the projection stops lifting.
"""

from __future__ import annotations

import pytest

from a2web.models import DECLARED_FIELDS_CAP, AskResponse, DeclaredEntity


def _page(entity_json: str) -> str:
    return f'<html><body><script type="application/ld+json">{entity_json}</script><p>body</p></body></html>'


async def _declared_from(html: str) -> DeclaredEntity | None:
    """Run the real comprehension ladder and return what it captured."""
    import time
    from dataclasses import dataclass, field

    from a2web.fetcher import _run_extraction_escalation
    from a2web.models import NextLink

    @dataclass
    class _Fc:
        content_md: str = ""
        final_url: str = "https://shop.example.com/p/1"
        start_perf: float = field(default_factory=time.perf_counter)
        next_links_handler: list[NextLink] = field(default_factory=list)
        content_candidates: list = field(default_factory=list)
        record_set: object | None = None
        record_count: int | None = None
        declared_entity: DeclaredEntity | None = None

    fc = _Fc()
    await _run_extraction_escalation(fc, raw_html=html)  # type: ignore[arg-type]
    return fc.declared_entity


async def test_a_declared_product_reaches_the_context() -> None:
    declared = await _declared_from(_page('{"@context":"https://schema.org","@type":"Product","name":"Widget","sku":"W-1","color":"red"}'))
    assert declared is not None
    assert declared.type == "Product"
    assert declared.source == "declared"
    assert declared.fields["name"] == "Widget"
    assert declared.fields["sku"] == "W-1"


async def test_an_unrecognised_type_is_relayed_verbatim() -> None:
    """ADR-0018 — the type is a LABEL, never a gate.

    `ProductGroup` is the measured case: 74 fields on nike.com, discarded whole
    by a closed vocabulary (`declaration_rate_v6`, 2026-08-03).
    """
    declared = await _declared_from(_page('{"@context":"https://schema.org","@type":"ProductGroup","name":"Air Max","variants":"3"}'))
    assert declared is not None
    assert declared.type == "ProductGroup", "an unknown type must survive, spelled as the page spelled it"
    assert declared.fields["name"] == "Air Max"


async def test_document_metadata_is_not_a_subject_declaration() -> None:
    """The other direction — an `Article` echo must NOT fill this field.

    Measured: `wikipedia-rust` declares `Article` (11 fields of publisher / logo
    / sameAs metadata) and scored **0.00 subject coverage on both reps**. It
    belongs on `structural_form`, not here. Without this test the blocklist
    could be emptied and every page would ship publisher chrome as its subject.
    """
    declared = await _declared_from(_page('{"@context":"https://schema.org","@type":"Article","headline":"H","author":{"name":"A"}}'))
    assert declared is None


async def test_the_richest_declaration_wins() -> None:
    """Most fields wins — the only tie-break that needs no opinion about types."""
    html = (
        "<html><body>"
        '<script type="application/ld+json">{"@type":"Offer","price":"10"}</script>'
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"N","sku":"S","brand":"B","color":"c","material":"m"}'
        "</script></body></html>"
    )
    declared = await _declared_from(html)
    assert declared is not None
    assert declared.type == "Product"


async def test_fields_are_capped_and_the_cut_is_declared() -> None:
    import json

    entity = {"@context": "https://schema.org", "@type": "Product"}
    entity |= {f"prop{i}": f"v{i}" for i in range(50)}
    declared = await _declared_from(_page(json.dumps(entity)))

    assert declared is not None
    assert len(declared.fields) == DECLARED_FIELDS_CAP
    # The remainder is COUNTED, not silently dropped — a caller must be able to
    # tell "the page states only this" from "a2web stopped relaying" (ADR-0009).
    assert declared.omitted == 50 - DECLARED_FIELDS_CAP
    # Publisher order, not a ranking (ADR-0012).
    assert next(iter(declared.fields)) == "prop0"


async def test_a_page_with_no_declaration_costs_nothing() -> None:
    assert await _declared_from("<html><body><p>just prose</p></body></html>") is None


# --------------------------------------------------------------------- #
# the wire
# --------------------------------------------------------------------- #


def _ask(**kw: object) -> AskResponse:
    from a2web.models import Confidence, FetchStatus

    base: dict[str, object] = {
        "url": "https://x/y",
        "status": FetchStatus.ok,
        "tier": "raw",
        "confidence": Confidence.high,
        "answer": "an answer",
    }
    return AskResponse(**(base | kw))  # type: ignore[arg-type]


def test_absent_declaration_is_absent_from_the_wire() -> None:
    """83-93% of pages declare nothing, so absence must cost zero bytes."""
    assert "declared_entity" not in _ask().model_dump()


def test_present_declaration_serialises_with_its_source() -> None:
    wire = _ask(
        declared_entity=DeclaredEntity(type="Recipe", fields={"name": "Lasagne", "cookTime": "PT1H"}),
    ).model_dump()

    entity = wire["declared_entity"]
    assert entity["type"] == "Recipe"
    # The caller never has to guess whether a2web READ this or WROTE it.
    assert entity["source"] == "declared"
    assert entity["fields"]["cookTime"] == "PT1H"
    # Nothing was cut, so no cut is claimed.
    assert "omitted" not in entity


def test_a_truncated_declaration_says_so_on_the_wire() -> None:
    wire = _ask(
        declared_entity=DeclaredEntity(type="Course", fields={"name": "ML"}, omitted=51),
    ).model_dump()
    assert wire["declared_entity"]["omitted"] == 51


@pytest.mark.parametrize("cap", [DECLARED_FIELDS_CAP])
def test_the_cap_is_the_measured_one(cap: int) -> None:
    """A witness, not a tautology — this pins the number to its measurement.

    `declared_cap_v5` found the knee at 20: cap 10 vs cap 20 is a significant
    loss (-0.089, CI [-0.175, -0.002]) and cap 20 vs uncapped is null (-0.018,
    CI [-0.052, +0.016]). Moving this constant without re-running that sweep
    silently discards the only evidence for it.
    """
    assert cap == 20
