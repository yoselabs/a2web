"""End-to-end synth escalation on a real JSON-LD listing.

Hepsiburada serves a JSON-LD `ItemList` of products with `offers.{price,
priceCurrency, url}` in the raw HTML. Trafilatura under-extracts it to a thin
nav smush; the JSON-in-script ladder rung must replace that with a synthetic
surface carrying prices and product urls, so the downstream extractor can
answer price questions and emit `try_url` drilldowns.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from a2web.fetcher import _run_extraction_escalation
from a2web.models import NextLink
from tests.fixtures import FIXTURES_DIR


@dataclass
class _FakeFc:
    content_md: str = ""
    final_url: str = ""
    start_perf: float = field(default_factory=time.perf_counter)
    next_links_handler: list[NextLink] = field(default_factory=list)


@pytest.mark.asyncio
async def test_hepsiburada_listing_synth_surfaces_prices_and_urls() -> None:
    html = (FIXTURES_DIR / "hepsiburada_listing.html").read_text()
    fc = _FakeFc(content_md="Giriş Yap Sepetim")  # thin nav-menu trafilatura output
    await _run_extraction_escalation(fc, raw_html=html)
    # price (with currency) now visible to the extractor
    assert "3690" in fc.content_md
    assert "TRY" in fc.content_md
    # product detail url present verbatim for try_url drilldowns
    assert "-pm-HBC" in fc.content_md
