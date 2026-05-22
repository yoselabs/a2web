"""v0.11: JSON synth also runs against browser-tier rendered DOM.

When the orchestrator escalates to the browser tier, `_escalate_browser`
installs the rendered markdown directly and re-gates — it never calls
`_phase_extract`. v0.11 wires `_maybe_synthesize_from_json` into the
escalator's install path so Trendyol-shape sites (where `__NEXT_DATA__`
is exposed post-hydration but trafilatura still captures only nav)
get the JSON synth treatment.

Direct unit test of `_maybe_synthesize_from_json` against a fake FC
carrying browser-style state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from a2web.fetcher import _maybe_synthesize_from_json
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


@dataclass
class _FakeFc:
    content_md: str = ""
    start_perf: float = field(default_factory=time.perf_counter)


@pytest.mark.asyncio
async def test_browser_rendered_thin_synth_replaces() -> None:
    """Browser tier produced thin content_md but rendered DOM carries
    __NEXT_DATA__ — synth runs and replaces."""
    html = (_FIX / "trendyol_search_next_data.html").read_text()
    fc = _FakeFc(content_md="Login Cart")  # thin browser output
    await _maybe_synthesize_from_json(fc, raw_html=html, extract_dur_start=0)
    assert "adidas CL TAPE BPK" in fc.content_md
    assert "Lenovo B210 Black" in fc.content_md


@pytest.mark.asyncio
async def test_browser_rendered_rich_synth_keeps_original() -> None:
    """Browser tier produced rich markdown — synth path doesn't replace."""
    html = (_FIX / "trendyol_search_next_data.html").read_text()
    rich = "## Real article\n\n" + "Lorem ipsum dolor sit amet. " * 200
    fc = _FakeFc(content_md=rich)
    await _maybe_synthesize_from_json(fc, raw_html=html, extract_dur_start=0)
    assert fc.content_md == rich


@pytest.mark.asyncio
async def test_browser_no_json_blob_keeps_thin_original() -> None:
    """Browser-rendered HTML without any JSON-in-script blobs → no synth."""
    fc = _FakeFc(content_md="thin")
    await _maybe_synthesize_from_json(fc, raw_html="<html><body><h1>plain rendered article</h1></body></html>", extract_dur_start=0)
    assert fc.content_md == "thin"
