"""fetch-response-diet: the lean `FetchResponse` wire envelope.

Every test drives the `fetch_raw` tool through the in-process MCP test
client (`call_wire` → the real formatter wrapper chain) and asserts on the
decoded wire dict — so the field-presence rules (empty-omission, failure /
debug tiers, TSV rendering) are verified on the exact payload an agent
receives, not on `.model_dump()`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from a2kit.testing import client as make_client

from a2web.models import NextLink
from a2web.server import app
from a2web.tiers import REGISTRY
from tests.test_ask_response import _MINIMAL_HTML, _RawStub

_FIX = Path(__file__).parent / "fixtures"


async def _fetch_raw_wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    body: bytes,
    raw_next_links: list | None = None,
    **kwargs: object,
) -> dict:
    """Invoke `fetch_raw` through the MCP transport; return the decoded wire dict."""
    monkeypatch.setitem(REGISTRY, "raw", _RawStub(body, raw_next_links))
    async with make_client(app) as client:
        wire = await client.call_wire("fetch_raw", **kwargs)
    return json.loads(wire)


# --------------------------------------------------------------------- #
# Empty-omission + failure-only status / narrative
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fetch_raw_success_omits_status_and_empty_optionals(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/raw",
        next_links=False,
    )
    # required fields always present
    for key in ("url", "tier", "confidence"):
        assert key in data
    # success → status / narrative / diagnostics_summary absent
    for key in ("status", "narrative", "diagnostics_summary"):
        assert key not in data, f"failure-only field {key!r} leaked on a successful fetch"
    # empty optionals absent (metadata-free body, no LLM, no links)
    for key in ("byline", "published", "meta", "links", "next_links", "operator_hints", "extraction", "extracted_answer", "original_url"):
        assert key not in data, f"empty optional {key!r} leaked onto the wire"


@pytest.mark.asyncio
async def test_fetch_raw_failure_carries_status_and_narrative(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIX / "cloudflare_block.html").read_bytes()
    data = await _fetch_raw_wire(monkeypatch, body=body, url="https://blocked.example/page")
    assert data["status"] == "failed"
    assert data["narrative"]
    assert data["diagnostics_summary"]


# --------------------------------------------------------------------- #
# Debug-only timing / cache / diagnostics / tokens
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fetch_raw_default_omits_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(monkeypatch, body=_MINIMAL_HTML, url="https://example.org/raw")
    for key in ("started_at", "total_ms", "cache", "diagnostics", "tokens"):
        assert key not in data


@pytest.mark.asyncio
async def test_fetch_raw_debug_includes_full_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(monkeypatch, body=_MINIMAL_HTML, url="https://example.org/raw", debug=True)
    for key in ("started_at", "total_ms", "cache", "tokens", "diagnostics"):
        assert key in data
    assert data["tokens"]["full"] == len(data["content_md"])


# --------------------------------------------------------------------- #
# TSV rendering for links / next_links
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fetch_raw_links_render_as_tsv(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIX / "blog.html").read_bytes()
    data = await _fetch_raw_wire(monkeypatch, body=body, url="https://example.org/post", include_links=True)
    tsv = data["links"]
    assert isinstance(tsv, str)
    assert tsv.splitlines()[0] == "anchor\thref\trole"
    assert len(tsv.splitlines()) >= 2  # header + at least one link


@pytest.mark.asyncio
async def test_fetch_raw_next_links_render_as_tsv(monkeypatch: pytest.MonkeyPatch) -> None:
    links = [
        NextLink(anchor="One", url="https://example.org/1", reason="r1", kind="drilldown"),
        NextLink(anchor="Two", url="https://example.org/2", reason="r2", kind="drilldown"),
    ]
    data = await _fetch_raw_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        raw_next_links=links,
        url="https://example.org/raw",
    )
    tsv = data["next_links"]
    assert isinstance(tsv, str)
    assert tsv.splitlines()[0] == "anchor\turl\treason"  # all-drilldown → no kind column
    assert len(tsv.splitlines()) == 3


@pytest.mark.asyncio
async def test_fetch_raw_empty_link_arrays_stay_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    data = await _fetch_raw_wire(
        monkeypatch,
        body=_MINIMAL_HTML,
        url="https://example.org/raw",
        include_links=True,
        next_links=False,
    )
    assert "links" not in data
    assert "next_links" not in data
