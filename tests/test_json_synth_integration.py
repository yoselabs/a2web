"""Integration tests for JSON-in-script synth wiring in `_phase_extract`.

Covers spec scenarios from openspec/changes/harsh-test-session-fixes/specs/extraction/spec.md
(JSON-synth subset).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from a2web.fetcher import _maybe_synthesize_from_json

_FIX = Path(__file__).parent / "fixtures"


@dataclass
class _FakeFc:
    """Minimal FetchContext shim — _maybe_synthesize_from_json only reads
    `content_md` + `start_perf` and writes `content_md`."""

    content_md: str = ""
    start_perf: float = field(default_factory=time.perf_counter)


@pytest.mark.asyncio
async def test_trendyol_thin_trafilatura_replaced_by_synthetic() -> None:
    """Trafilatura output thin → JSON path runs → synthetic replaces."""
    html = (_FIX / "trendyol_search_next_data.html").read_text()
    fc = _FakeFc(content_md="Login Cart")  # thin nav-menu output
    await _maybe_synthesize_from_json(fc, raw_html=html, extract_dur_start=0)
    assert "| name |" in fc.content_md or "| brand |" in fc.content_md
    assert "adidas CL TAPE BPK" in fc.content_md
    assert "Lenovo B210 Black" in fc.content_md


@pytest.mark.asyncio
async def test_ld_json_product_thin_path_synthesizes_entity() -> None:
    """LD-JSON Product → synthetic per-entity markdown."""
    html = (_FIX / "ld_json_product.html").read_text()
    fc = _FakeFc(content_md="Osprey Farpoint 70 Travel pack.")  # below threshold sentences
    await _maybe_synthesize_from_json(fc, raw_html=html, extract_dur_start=0)
    assert "Product:" in fc.content_md
    assert "Osprey Farpoint 70" in fc.content_md
    assert "aggregateRating" in fc.content_md


@pytest.mark.asyncio
async def test_fat_trafilatura_output_skips_synth_path() -> None:
    """Above the thinness threshold → JSON path does not run, original kept."""
    html = (_FIX / "trendyol_search_next_data.html").read_text()
    original = "Lorem ipsum. " * 300  # >2KB and many sentences
    fc = _FakeFc(content_md=original)
    await _maybe_synthesize_from_json(fc, raw_html=html, extract_dur_start=0)
    assert fc.content_md == original


@pytest.mark.asyncio
async def test_no_payloads_keeps_original() -> None:
    """Page with no JSON-in-script blobs → no-op."""
    html = "<html><body><h1>plain</h1></body></html>"
    fc = _FakeFc(content_md="thin")
    await _maybe_synthesize_from_json(fc, raw_html=html, extract_dur_start=0)
    assert fc.content_md == "thin"


@pytest.mark.asyncio
async def test_low_yield_synth_kept_original_below_ratio() -> None:
    """Synth produces something but <2x the original → keep original."""
    html = (
        '<html><body>'
        '<script type="application/ld+json">{"@type":"Product","name":"P","brand":"B","offers":{"price":1}}</script>'
        '</body></html>'
    )
    # Original already fairly long — synthetic must beat 2x threshold to replace.
    original = "x" * 500
    fc = _FakeFc(content_md=original)
    await _maybe_synthesize_from_json(fc, raw_html=html, extract_dur_start=0)
    # Synth is roughly ~200 chars, original is 500, 2x = 1000 → keep original
    assert fc.content_md == original


@pytest.mark.asyncio
async def test_yandex_market_generic_fallback() -> None:
    """When LD-JSON is weak (WebSite schema, no rows), generic payload wins."""
    html = (_FIX / "yandex_market_generic.html").read_text()
    fc = _FakeFc(content_md="Рюкзак")  # thin
    await _maybe_synthesize_from_json(fc, raw_html=html, extract_dur_start=0)
    assert "Mark Ryden" in fc.content_md
    assert "Xiaomi" in fc.content_md
