"""Integration tests for the JSON-in-script source of the extraction ladder.

`_run_extraction_escalation` runs unconditionally after every extraction; the
JSON-in-script source is the first ladder rung and self-gates on the presence
of embedded JSON.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from a2web.fetcher import _run_extraction_escalation
from a2web.models import NextLink
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


@dataclass
class _FakeFc:
    """Minimal FetchContext shim — the escalation ladder reads
    content_md / start_perf / final_url and writes content_md /
    next_links_handler."""

    content_md: str = ""
    final_url: str = ""
    start_perf: float = field(default_factory=time.perf_counter)
    next_links_handler: list[NextLink] = field(default_factory=list)
    # Mirrors `FetchContext`: the escalation installs a JSON-LD-derived record
    # set here when the DOM miner found none (ADR-0015 listing index).
    record_set: object | None = None
    record_count: int | None = None


@pytest.mark.asyncio
async def test_trendyol_thin_trafilatura_replaced_by_json_synth() -> None:
    """Trafilatura output thin → JSON source runs → synthetic replaces."""
    html = (_FIX / "trendyol_search_next_data.html").read_text()
    fc = _FakeFc(content_md="Login Cart")  # thin nav-menu output
    await _run_extraction_escalation(fc, raw_html=html)
    assert "adidas CL TAPE BPK" in fc.content_md
    assert "Lenovo B210 Black" in fc.content_md


@pytest.mark.asyncio
async def test_ld_json_product_thin_path_synthesizes_entity() -> None:
    """LD-JSON Product → synthetic per-entity markdown."""
    html = (_FIX / "ld_json_product.html").read_text()
    fc = _FakeFc(content_md="Osprey Farpoint 70.")
    await _run_extraction_escalation(fc, raw_html=html)
    assert "Osprey Farpoint 70" in fc.content_md
    assert "aggregateRating" in fc.content_md


@pytest.mark.asyncio
async def test_well_extracted_page_ladder_self_gates() -> None:
    """The ladder runs on every page — a plain article has no embedded JSON
    and no record region, so every rung self-gates and content_md stands."""
    article = "This is a complete article sentence with real prose content here. " * 15
    html = f"<html><body><article>{article}</article></body></html>"
    fc = _FakeFc(content_md=article)
    await _run_extraction_escalation(fc, raw_html=html)
    assert fc.content_md == article


@pytest.mark.asyncio
async def test_no_source_helps_falls_through_unchanged() -> None:
    """No JSON payloads and no record region → content_md left unchanged."""
    html = "<html><body><h1>plain</h1><p>tiny</p></body></html>"
    fc = _FakeFc(content_md="thin")
    await _run_extraction_escalation(fc, raw_html=html)
    assert fc.content_md == "thin"
    assert fc.next_links_handler == []


@pytest.mark.asyncio
async def test_json_candidate_shorter_than_original_is_kept() -> None:
    """Sub-floor prose loses to a structured candidate, regardless of length.

    Reversed 2026-08-02 with the retirement of relative-length selection. This
    previously asserted that a short JSON synth "does not win" against a longer
    original — the same length rule retired in `menu._wire_content_md`, stated
    here in a second file.

    The surviving line is the FLOOR, not a comparison: 300 chars is below
    `LENGTH_FLOOR`, which is the project-wide way of saying "this is not content"
    (a nav/footer fragment). Gluing a fragment already classified as non-content
    onto the answer would make the floor mean nothing, so sub-floor prose is
    still dropped. What no longer happens is dropping ABOVE-floor prose, or
    dropping a short structured payload, because one rendered longer.
    """
    html = (
        "<html><body>"
        '<script type="application/ld+json">{"@type":"Product","name":"P"}</script>'
        "<p>" + ("word " * 2000) + "</p>"
        "</body></html>"
    )
    original = "x" * 300  # BELOW LENGTH_FLOOR — a fragment, not an article
    fc = _FakeFc(content_md=original)
    await _run_extraction_escalation(fc, raw_html=html)
    assert fc.content_md == "## Product: P\n- **name:** P"
    assert original not in fc.content_md


@pytest.mark.asyncio
async def test_yandex_market_generic_fallback() -> None:
    """When LD-JSON is weak, the generic framework-state payload wins."""
    html = (_FIX / "yandex_market_generic.html").read_text()
    fc = _FakeFc(content_md="Рюкзак")
    await _run_extraction_escalation(fc, raw_html=html)
    assert "Mark Ryden" in fc.content_md
    assert "Xiaomi" in fc.content_md
