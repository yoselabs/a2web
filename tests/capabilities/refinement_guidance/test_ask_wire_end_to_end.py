"""content-aware refinement: end-to-end through the real MCP transport.

Drives `ask` over a listing body with a stub LLM returning a router-shape
envelope, and asserts the decoded wire (the exact payload an agent receives)
carries `refinement_axes` + the `content_guidance` hint on a partial listing,
and drops the axes when the listing is complete. Exercises the full pipeline
including `_apply_llm_listing_oracle` (the LLM-side oracle fallback).
"""

from __future__ import annotations

import json

import pytest
from a2kit.testing import client as make_client

from a2web.llm_resource import LlmExtractorResource
from a2web.server import build_app
from a2web.state import AppState
from a2web.tiers import REGISTRY
from tests.capabilities.ask_response.test_ask_response import _extractor, _RawStub
from tests.capabilities.listing_completeness.test_listing_completeness import _listing_html


async def _ask_listing_wire(monkeypatch: pytest.MonkeyPatch, *, body: bytes, answer: str, **ask_kwargs: object) -> dict:
    """Drive `ask` over `body` with the LLM stub returning `answer`; decode the wire."""
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(body))
    app = build_app()
    state = await app.container().get(AppState)
    fake = _extractor(state, answer=answer)
    app.provide(LlmExtractorResource, lambda: fake)
    async with make_client(app) as client:
        wire = await client.call_wire("query", **ask_kwargs)
    return json.loads(wire)


def _router_answer(*, total_seen: int, axes: list[dict]) -> str:
    return json.dumps(
        {
            "answer": "The cheapest crimping tools shown range 270-495 TL.",
            "structural_form": "listing",
            "shape": "records",
            "item_total_seen": total_seen,
            "refinement_axes": axes,
        }
    )


_AXES = [
    {"dimension": "price floor", "how": "add a minimum price to skip the cheapest tier"},
    {"dimension": "sort order", "how": "sort by rating instead of price"},
]


@pytest.mark.asyncio
async def test_partial_listing_wire_carries_axes_and_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    # 6 records parsed, model read a 1123 total (no regex oracle in the body) →
    # LLM-side oracle fallback flags partial → axes + guidance ride the wire.
    data = await _ask_listing_wire(
        monkeypatch,
        body=_listing_html(6),
        answer=_router_answer(total_seen=1123, axes=_AXES),
        url="https://shop.example/ara?q=crimp&siralama=artanFiyat",
        query="which crimping tool is best?",
    )
    assert data["refinement_axes"] == _AXES
    assert data["items_total"] == 1123
    assert data["items_loaded"] == 6
    assert "content_guidance" in [h["code"] for h in data["operator_hints"]]
    # dimensional discipline: no axis value names a specific product/brand row
    for axis in data["refinement_axes"]:
        assert set(axis) == {"dimension", "how"}


@pytest.mark.asyncio
async def test_complete_listing_keeps_criteria_drops_partial_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    # Complete listing (total meets count): no partial signal (no items_total),
    # but criteria/axes STILL surface — they are decoupled from completeness
    # (answer-neutrality-for-selection). The gate is the listing kind, not partial.
    data = await _ask_listing_wire(
        monkeypatch,
        body=_listing_html(6),
        answer=_router_answer(total_seen=6, axes=_AXES),
        url="https://shop.example/ara?q=crimp",
        query="which crimping tool is best?",
    )
    assert data["refinement_axes"] == _AXES
    assert "items_total" not in data
