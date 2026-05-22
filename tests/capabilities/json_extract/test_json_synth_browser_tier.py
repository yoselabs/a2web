"""The extraction-escalation ladder also runs against browser-rendered DOM.

`_escalate_browser` installs the rendered markdown and, before re-gating,
runs `_run_extraction_escalation` on the rendered HTML — so a Trendyol-shape
site (`__NEXT_DATA__` exposed post-hydration but trafilatura captures only
nav chrome) gets the JSON synth treatment on the browser path too.
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
    content_md: str = ""
    final_url: str = ""
    start_perf: float = field(default_factory=time.perf_counter)
    next_links_handler: list[NextLink] = field(default_factory=list)


@pytest.mark.asyncio
async def test_browser_rendered_thin_synth_replaces() -> None:
    """Browser tier produced thin content_md but the rendered DOM carries
    __NEXT_DATA__ — the JSON source runs and replaces."""
    html = (_FIX / "trendyol_search_next_data.html").read_text()
    fc = _FakeFc(content_md="Login Cart")
    await _run_extraction_escalation(fc, raw_html=html)
    assert "adidas CL TAPE BPK" in fc.content_md
    assert "Lenovo B210 Black" in fc.content_md


@pytest.mark.asyncio
async def test_browser_rendered_rich_synth_keeps_original() -> None:
    """Browser tier produced well-extracted markdown (high recall) — ladder skipped."""
    rich = "## Real article\n\n" + "Lorem ipsum dolor sit amet consectetur. " * 60
    html = f"<html><body><article>{rich}</article></body></html>"
    fc = _FakeFc(content_md=rich)
    await _run_extraction_escalation(fc, raw_html=html)
    assert fc.content_md == rich


@pytest.mark.asyncio
async def test_browser_no_json_blob_keeps_thin_original() -> None:
    """Browser-rendered HTML with no JSON blob and no record region → no-op."""
    fc = _FakeFc(content_md="thin")
    await _run_extraction_escalation(
        fc, raw_html="<html><body><h1>plain rendered article</h1></body></html>"
    )
    assert fc.content_md == "thin"
